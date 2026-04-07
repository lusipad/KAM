# KAM 便携运行包

这个压缩包已经内置前端 `app/dist`，本机只需要 Python 3；不需要再安装 Node。

最简单的入口是：

```text
kam.cmd
```

执行后会让你选择：

- 打开 KAM 工作台
- 进入 operator 菜单
- 播种 demo 数据
- 查看状态
- 持续 watch
- 跑本地验证

## Windows

```powershell
pwsh -ExecutionPolicy Bypass -File .\install.ps1
.\kam.cmd
```

启动后访问 `http://127.0.0.1:8000`。

如果你要人工值守或干预：

```powershell
pwsh -File .\kam-operator.ps1 menu
```

## macOS / Linux

```bash
bash ./install.sh
bash ./run.sh
```

启动后访问 `http://127.0.0.1:8000`。

如果需要 operator CLI，但本机没有 `pwsh`，可直接执行：

```bash
./.venv/bin/python backend/scripts/operator_cli.py menu
```

## 说明

- 首次安装会创建 `.venv/` 并安装 `backend/requirements.txt`
- 若当前目录没有 `.env`，安装脚本会自动从 `.env.example` 复制一份
- 数据库与运行产物默认写入 `backend/storage/`
- 如果你已经有预设的 Python，可在安装前设置 `PYTHON_BIN`
