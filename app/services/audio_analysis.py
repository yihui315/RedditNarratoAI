"""
音频分析服务：Whisper 转写 + 高光检测
- Whisper 自动生成视频内容描述（无需手动填写）
- 高光/能量峰值检测找精彩片段（借鉴 AutoClip）
"""
import os
import numpy as np
from loguru import logger

__all__ = ["transcribe_video", "find_highlight_segments", "analyze_video_content"]


def transcribe_video(
    video_path: str,
    model_size: str = "medium",
    language: str = "zh",
    progress_callback=None,
) -> dict:
    """
    使用 Whisper 自动转写视频音频，生成内容描述

    Args:
        video_path: 视频文件路径
        model_size: Whisper 模型大小 (tiny/base/small/medium/large)
                     medium 平衡精度和速度，large 最精准但慢
        language: 语言代码，zh=中文
        progress_callback: (step, percent)

    Returns:
        dict: {
            "success": bool,
            "transcript": str,       # 完整转写文本
            "segments": list,         # Whisper 时间戳片段
            "summary": str,           # AI 摘要（用于内容描述）
            "duration": float,        # 音频时长
            "error": str
        }
    """
    result = {
        "success": False,
        "transcript": "",
        "segments": [],
        "summary": "",
        "duration": 0.0,
        "error": "",
    }

    try:
        _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)
        _update("正在加载 Whisper 模型...", 5)

        from faster_whisper import WhisperModel

        # 模型映射：可用 size → 下载用
        available_sizes = ("tiny", "base", "small", "medium", "large-v2", "large-v3")
        if model_size not in available_sizes:
            model_size = "medium"

        # 使用 CPU int8 推理（兼容所有机器）
        _update(f"Whisper {model_size} 初始化中（首次慢）...", 10)
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=os.path.expanduser("~/.cache/whisper"),
        )
        _update("Whisper 模型加载完成", 15)

        # 转写
        _update("正在进行语音识别...", 20)
        segments, info = model.transcribe(
            video_path,
            language=language,
            vad_filter=True,        # 语音活动检测，过滤静音
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=True,
        )

        segment_list = []
        transcript_parts = []

        for seg in segments:
            seg_dict = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            segment_list.append(seg_dict)
            transcript_parts.append(seg.text.strip())

            # 进度更新（每10个片段）
            if len(segment_list) % 10 == 0:
                pct = min(20 + int(60 * seg.end / max(info.duration, 1)), 80)
                _update(f"已识别 {len(segment_list)} 段...", pct)

        full_transcript = " ".join(transcript_parts)
        result["transcript"] = full_transcript
        result["segments"] = segment_list
        result["whisper_segments"] = segment_list  # Alias for pipeline access
        result["duration"] = info.duration

        _update("正在生成内容摘要...", 85)

        # 用 AI 总结转写内容，生成精炼的内容描述
        if full_transcript.strip():
            result["summary"] = _summarize_transcript(full_transcript, segment_list, language)
            _update("Whisper 识别完成", 100)
        else:
            result["summary"] = "（视频无语音内容，仅有背景音）"

        result["success"] = True
        logger.info(f"[whisper] transcribed {info.duration:.0f}s video, {len(segment_list)} segments")

    except Exception as e:
        logger.exception("[whisper] transcription error")
        result["error"] = str(e)

    return result


def _summarize_transcript(transcript: str, segments: list, language: str = "zh") -> str:
    """用 AI 总结转写文本，生成 100-200 字的内容描述"""
    try:
        from app.services.llm import generate_response_from_config

        # 提取关键片段（前中后各取几段，保持上下文）
        n = len(segments)
        if n == 0:
            return ""
        sample_indices = (
            list(range(0, min(3, n // 3)))
            + list(range(n // 3, min(6, 2 * n // 3)))
            + list(range(max(0, 2 * n // 3 - 3), n))
        )
        sample_segments = [segments[i]["text"] for i in sample_indices if i < len(segments)]
        context = "；".join(sample_segments[:15])  # 最多15段

        prompt = (
            f"以下是一段视频的语音转写内容（可能有少量识别误差）：\n\n"
            f"【转写片段】{context}\n\n"
            f"请根据以上内容，生成一段简洁的视频内容描述（100-200字），"
            f"用于帮助AI生成更精准的解说文案。描述要涵盖：\n"
            f"1. 视频的主题或场景\n"
            f"2. 主要讨论的内容或事件\n"
            f"3. 说话人的身份或角色（如果能判断）\n"
            f"4. 视频的风格或氛围\n\n"
            f"直接输出描述内容，不要加标题或前缀。"
        )

        summary = generate_response_from_config(prompt, system_prompt="你是一个视频内容分析师，擅长从语音转写中提取视频主题和关键信息。")
        return summary.strip()

    except Exception as e:
        logger.warning(f"[_summarize_transcript] failed: {e}")
        # Fallback: 截取转写前200字
        return transcript[:200] + "..." if len(transcript) > 200 else transcript


def find_highlight_segments(
    video_path: str,
    min_peak_gap: float = 45.0,
    energy_percentile: float = 0.75,
    min_segment_duration: float = 60.0,
    max_segment_duration: float = 240.0,
    highlight_coverage: float = 0.6,
) -> list:
    """
    AutoClip 式高光检测：识别音频能量峰值区间作为精彩片段

    原理：
    - 把音频切成小窗口（1秒），计算每个窗口的能量（RMSE）
    - 找到能量最高的那些区间（高光区域）
    - 用这些高光区间来决定分段点
    - 静音点依然作为自然切分，但优先保留高光区域完整性

    Args:
        video_path: 视频路径
        min_peak_gap: 两个高光峰之间的最小间隔（秒），避免切太碎
        energy_percentile: 能量阈值百分位，高于这个值视为高光（0.75=前25%高能）
        min_segment_duration: 最短片段时长
        max_segment_duration: 最长片段时长
        highlight_coverage: 每个片段中高光区域应占的比例（0.6=60%以上是有内容的）

    Returns:
        list: [(start, end, energy), ...] 每个片段的时间范围+能量值
    """
    try:
        import librosa
    except ImportError:
        logger.warning("[highlights] librosa not installed, using simple amplitude")
        return _find_highlights_simple(video_path, min_peak_gap, min_segment_duration, max_segment_duration)

    try:
        _load_audio(video_path)
        y, sr = _load_audio(video_path)

        # ── Step 1: 计算每帧 RMS 能量 ───────────────────────────
        hop_length = 512
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        times = librosa.times_like(rms, sr=sr, hop_length=hop_length)

        # ── Step 2: 找到能量峰值点 ─────────────────────────────
        # 计算滚动最大值和能量阈值
        from scipy.signal import find_peaks

        # 用中值滤波平滑，去掉瞬时尖峰
        from scipy.ndimage import median_filter
        rms_smooth = median_filter(rms, size=5)

        # 找峰值：高于 energy_percentile 且间距够大
        threshold = np.percentile(rms_smooth, energy_percentile * 100)
        peaks, properties = find_peaks(
            rms_smooth,
            height=threshold,
            distance=int(min_peak_gap * sr / hop_length),
            prominence=0.02,
        )

        peak_times = times[peaks]
        peak_energies = rms_smooth[peaks]

        logger.info(f"[highlights] Found {len(peaks)} energy peaks above {threshold:.4f}")

        if len(peak_times) == 0:
            logger.warning("[highlights] No peaks found, using uniform segments")
            return _uniform(times[-1] if len(times) > 0 else 300, min_segment_duration, max_segment_duration)

        # ── Step 3: 构建高光区间（峰值 ± 窗口） ─────────────────
        window = 30.0  # 每个峰值扩展为 60 秒窗口
        highlight_regions = []
        for pt in peak_times:
            h_start = max(0, pt - window / 2)
            h_end = min(times[-1], pt + window / 2)
            highlight_regions.append((h_start, h_end))

        # ── Step 4: 合并重叠的高光区间 ──────────────────────────
        highlight_regions = _merge_overlapping(highlight_regions)

        # ── Step 5: 构建最终片段（在静音点 + 高光区间之间切分） ─
        # 结合静音检测的结果来定位更精确的切分点
        try:
            silence_boundaries = _get_silence_for_highlights(
                video_path, min_silence_duration=0.8, silence_threshold_db=-40.0
            )
        except Exception:
            silence_boundaries = []

        # 以高光区间为基础，用静音点作为辅助切分
        final_segments = _build_segments_from_highlights(
            highlight_regions=highlight_regions,
            silence_boundaries=silence_boundaries,
            min_segment_duration=min_segment_duration,
            max_segment_duration=max_segment_duration,
            total_duration=times[-1],
        )

        logger.info(f"[highlights] Built {len(final_segments)} final segments")
        for i, (s, e, en) in enumerate(final_segments):
            logger.info(f"  clip_{i:03d}: {s:.1f}s-{e:.1f}s (dur={e-s:.1f}s, energy={en:.4f})")

        return final_segments

    except Exception as e:
        logger.exception("[highlights] Error")
        return _uniform(300, min_segment_duration, max_segment_duration)


def _load_audio(video_path: str):
    """从视频提取音频（mp3格式临时保存）"""
    import tempfile, subprocess, os

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                "-ar", "16000", "-ac", "1",
                tmp.name
            ],
            capture_output=True, timeout=300,
        )
        import librosa
        y, sr = librosa.load(tmp.name, sr=None, mono=True)
    finally:
        os.unlink(tmp.name)
    return y, sr


def _merge_overlapping(regions: list) -> list:
    """合并重叠的时间区间"""
    if not regions:
        return []
    sorted_regions = sorted(regions, key=lambda x: x[0])
    merged = [sorted_regions[0]]
    for start, end in sorted_regions[1:]:
        if start <= merged[-1][1] + 1.0:  # 1秒内重叠视为连续
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _get_silence_for_highlights(video_path: str, min_silence_duration: float, silence_threshold_db: float) -> list:
    """获取静音边界（辅助高光切分）"""
    import librosa, numpy as np

    y, sr = _load_audio(video_path)
    duration = len(y) / sr
    db = librosa.util.amplitude_to_db(np.abs(y), ref=np.max)
    frame_dur = 1.0 / sr

    is_silence = db < silence_threshold_db
    silence_points = []
    in_silence = False
    silence_start = 0

    for i, silent in enumerate(is_silence):
        t = i * frame_dur
        if silent and not in_silence:
            in_silence = True
            silence_start = t
        elif not silent and in_silence:
            in_silence = False
            dur = t - silence_start
            if dur >= min_silence_duration:
                silence_points.append((silence_start, t))

    return silence_points


def _build_segments_from_highlights(
    highlight_regions: list,
    silence_boundaries: list,
    min_segment_duration: float,
    max_segment_duration: float,
    total_duration: float,
) -> list:
    """从高光区间 + 静音边界构建最终片段"""
    # 所有潜在切分点（静音中点 + 高光区间端点）
    breakpoints = set()
    for s, e in silence_boundaries:
        breakpoints.add((s + e) / 2)
    for h_start, h_end in highlight_regions:
        breakpoints.add(h_start)
        breakpoints.add(h_end)
    breakpoints = sorted([bp for bp in breakpoints if 0 < bp < total_duration])

    # 添加起点和终点
    all_points = [0.0] + breakpoints + [total_duration]

    # 合并太近的点（< min_segment_duration）
    segments = []
    seg_start = all_points[0]
    for t in all_points[1:]:
        if t - seg_start >= min_segment_duration:
            segments.append((seg_start, t))
            seg_start = t
        else:
            # 合并到下一个
            pass

    # 处理最后一个片段
    if total_duration - seg_start > min_segment_duration * 0.3:
        if segments and (seg_start - segments[-1][1]) < min_segment_duration * 0.5:
            # 合并
            segments[-1] = (segments[-1][0], total_duration)
        else:
            segments.append((seg_start, total_duration))

    # 限制最大长度
    final = []
    for start, end in segments:
        while end - start > max_segment_duration:
            mid = start + max_segment_duration / 2
            final.append((start, mid, 0.5))
            start = mid
        final.append((start, end, 0.5))

    return final


def _find_highlights_simple(
    video_path: str,
    min_peak_gap: float,
    min_segment_duration: float,
    max_segment_duration: float,
) -> list:
    """Fallback: 用 moviepy 简化版能量检测"""
    from moviepy import AudioClip
    import numpy as np

    try:
        audio = AudioClip.from_file(video_path)
        duration = audio.duration
        n_samples = int(duration * 2)
        times = np.linspace(0, duration, n_samples)

        def get_energy(t):
            frame = audio.get_frame(t)
            return np.sqrt(np.mean(frame ** 2))

        energies = [get_energy(t) for t in times]
        threshold = np.percentile(energies, 75)

        # 找峰值
        peaks = [(times[i], energies[i]) for i in range(1, len(energies) - 1)
                 if energies[i] > threshold
                 and energies[i] > energies[i - 1]
                 and energies[i] > energies[i + 1]
                 and times[i] - (peaks[-1][0] if peaks else 0) > min_peak_gap]

        if len(peaks) < 2:
            return _uniform(duration, min_segment_duration, max_segment_duration)

        regions = [(max(0, p - 30), min(duration, p + 30)) for p, _ in peaks]
        regions = _merge_overlapping(regions)

        return _build_segments_from_highlights(
            highlight_regions=regions,
            silence_boundaries=[],
            min_segment_duration=min_segment_duration,
            max_segment_duration=max_segment_duration,
            total_duration=duration,
        )
    except Exception:
        return _uniform(300, min_segment_duration, max_segment_duration)


def _uniform(duration: float, min_seg: float, max_seg: float) -> list:
    segments = []
    start = 0.0
    while start < duration:
        end = min(start + max_seg, duration)
        segments.append((start, end, 0.5))
        start = end
    return segments


def analyze_video_content(
    video_path: str,
    progress_callback=None,
) -> dict:
    """
    综合分析：Whisper 转写 + 高光检测
    自动生成视频内容描述 + 推荐分段点

    Returns:
        dict: {
            "success": bool,
            "description": str,      # AI 生成的视频内容描述
            "transcript": str,        # Whisper 完整转写
            "segments": list,         # 推荐片段 [(start, end), ...]
            "total_duration": float,
            "error": str
        }
    """
    result = {
        "success": False,
        "description": "",
        "transcript": "",
        "segments": [],
        "total_duration": 0.0,
        "error": "",
    }

    _update = lambda msg, pct: progress_callback and progress_callback(msg, pct)

    try:
        # Step 1: Whisper 转写（同时生成描述）
        _update("正在分析视频内容（Whisper转写）...", 10)
        whisper_result = transcribe_video(
            video_path=video_path,
            model_size="medium",
            language="zh",
            progress_callback=progress_callback,
        )

        if not whisper_result["success"]:
            result["error"] = whisper_result.get("error", "Whisper 转写失败")
            return result

        result["transcript"] = whisper_result["transcript"]
        result["description"] = whisper_result["summary"]
        result["total_duration"] = whisper_result["duration"]

        # Step 2: 高光检测找分段点
        _update("正在检测高光片段...", 90)
        highlight_segments = find_highlight_segments(
            video_path=video_path,
            min_peak_gap=45.0,
            energy_percentile=0.75,
            min_segment_duration=60.0,
            max_segment_duration=240.0,
        )

        result["segments"] = [(s, e) for s, e, _ in highlight_segments]
        result["success"] = True

        _update("视频内容分析完成", 100)
        logger.info(f"[analyze_video] {result['total_duration']:.0f}s, {len(result['segments'])} segments, desc={result['description'][:50]}...")

    except Exception as e:
        logger.exception("[analyze_video] Error")
        result["error"] = str(e)

    return result
