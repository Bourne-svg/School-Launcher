# 申请书架 / SchoolLauncher

Windows 院校申请入口管理工具：自由编辑网址和账号资料、本地加密保存、Chrome 辅助填入。

**[下载 Windows x64 便携版 ZIP](https://github.com/Bourne-svg/School-Launcher/releases/download/v0.0.2/SchoolLauncher-v0.0.2-windows-x64.zip)** · [版本与校验文件](https://github.com/Bourne-svg/School-Launcher/releases/latest)

## 开始使用

1. 下载 ZIP，右键“全部解压”到可写入的固定目录。
2. 双击 `SchoolLauncher.exe`。无需 Python、Conda 或命令行。请保留整个目录，不能只复制 EXE。
3. 首次账号库为空，点击“添加第一个申请入口”，填写名称、网址、账号、密码并保存。
4. 在“应用设置”中创建桌面快捷方式，并按内置说明加载随包 Chrome 扩展、验证连接。

支持 Windows 10/11 x64，界面依赖 Microsoft Edge WebView2 运行时；缺少时程序会引导前往微软官方安装页面。自动填入需要 Google Chrome。完整步骤见 [使用说明](使用说明.md)。

## 功能与边界

- 新增、编辑、删除、搜索院校和工具入口；支持账号密码、申请编号与邮箱、邮箱链接三种登录方式。
- 资料使用当前 Windows 用户 DPAPI 加密，位于 `%LOCALAPPDATA%\SchoolLauncher`；发布包不含个人账号库。复制加密文件到其他用户或电脑通常无法解密。
- 已适配：网易邮箱、香港理工大学、香港大学、香港中文大学、香港科技大学、南洋理工大学、点头算力云。
- 其他网站可自由保存网址和资料，通过“仅打开网站”及复制使用；自动填入仅限既有适配规则。
- Chrome 扩展已包含在下载包中，首次需要手动启用开发者模式并加载。尚未上架 Chrome 商店，不会静默修改浏览器策略。
- 不自动提交登录、不处理验证码或发送邮件；没有账号云同步或遥测。填入后网站可以读取表单数据。
- 支持托盘、窗口置顶、可选自启动；关闭窗口收至托盘，可从托盘退出。

## 构建与测试

使用 Windows x64、Python 3.11，安装 `requirements-lock.txt`，在干净源码目录执行 `./build.ps1 -Python python`。输出包含桌面程序及独立 Native Messaging 主机。`tools/package_release.py` 从明确的源码清单建立干净构建目录、运行构建并生成 ZIP 与 SHA-256 文件。

```powershell
python -m pytest tests/test_core.py tests/test_autofill.py tests/test_portable.py -q
python tests/check_content.py
node tests/test_worker.mjs
python tests/check_ui.py
python tests/check_native.py
python tools/package_release.py --work-dir C:/SchoolLauncher-build --python python
```

测试使用虚构凭据；本机原生 UI 测试会显示独立测试窗口，不连接正式账号库。测试证据及未验证范围见 [验收记录](验收记录.md)。

## 连接与权限

应用首次启动仅注册当前用户的 `HKCU\Software\Google\Chrome\NativeMessagingHosts\cn.schoollauncher.autofill`，无需管理员权限。扩展仅访问已适配站点，固定扩展 ID 与 Native Messaging 主机对应。凭据任务有效期 120 秒、只能领取一次，绑定标签页与来源；扩展不保存凭据。

“清理本机连接”只移除指向当前程序的注册和快捷方式，保留账号数据。随后退出程序、从 Chrome 移除扩展、删除解压目录即可。再次运行程序会重新注册连接。
