# Skill: /batch-process

## 概述
批量处理多个 Reddit URL，并行生成视频。

## 输入
- URL 列表文件（每行一个 URL）
- 或命令行多个 URL 参数

## 输出
- 每个 URL 对应一个视频输出
- 汇总报告（成功/失败统计）

## 逻辑
1. 读取 URL 列表（文件或参数）
2. `concurrent.futures.ProcessPoolExecutor` 并行处理
3. 每个 worker 独立运行完整 pipeline（`RedditVideoPipeline.run()`）
4. 每个视频独立验证（Verification Loop）
5. 汇总结果:
   - 成功数 / 总数
   - 失败 URL + 错误信息
   - 总耗时

## Verification
- 每个视频单独通过 `verify_video()` 检查
- 总体完成率 ≥ 80%（低于则警告）
- 错误日志完整记录

## CLI 用法
```bash
# 从文件读取 URL
python cli.py batch urls.txt --workers 2

# 直接传入多个 URL
python cli.py batch url1 url2 url3

# 指定输出目录
python cli.py batch urls.txt --output-dir ./my_output
```

## 实现文件
- `app/batch.py` → `BatchProcessor` 类
- `cli.py` → `batch` 子命令

## 配置
```toml
[batch]
max_workers = 2
retry_failed = true
```
