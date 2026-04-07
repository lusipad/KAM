KAM Windows Release
===================

这是 KAM 的 Windows 即开即用版本。

使用方式
--------
1. 解压整个压缩包
2. 双击 KAM.exe
3. 浏览器会自动打开 http://127.0.0.1:8000

关闭方式
--------
- 回到 KAM.exe 的控制台窗口
- 按 Ctrl+C

数据位置
--------
- storage\kam-harness.db
- storage\runs\

可选配置
--------
- 如需覆盖默认配置，把 .env.example 复制为 .env 后再修改

重要说明
--------
- 这个 release 包不需要本机安装 Python 或 Node
- 如果你要让 KAM 真正调用 codex / claude-code 执行任务，这些 agent CLI 仍然需要在你的机器上可用
