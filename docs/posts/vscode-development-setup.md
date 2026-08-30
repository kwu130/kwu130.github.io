---
title: "VS Code 开发环境配置：C/C++、Python 与远程开发"
description: "用一组职责清晰的扩展和少量可迁移设置，搭建适合 C/C++、Python、CMake 与 Remote SSH 的开发环境。"
publishedAt: 2024-07-01
updatedAt: 2026-08-30
tags:
  - "开发工具"
  - "VS Code"
slug: "vscode-development-setup"
legacyPaths:
  - "/post/vscode-cha-jian-he-kai-fa-she-zhi.html"
issueNumber: 2
draft: false
---

VS Code 的扩展很多，但“安装得多”并不等于“开发体验更好”。真正稳定的开发环境应该满足三个条件：每个扩展职责明确、项目约定能够进入版本控制、换一台电脑后仍然容易重建。

下面给出一套偏克制的配置，覆盖 C/C++、Python、CMake 和远程 Linux 开发。重点不是列出所有“好用扩展”，而是说明语言服务、构建系统、格式化工具和工作区配置分别应该负责什么。扩展名称和设置可能随版本调整，安装前应以 [VS Code 官方文档](https://code.visualstudio.com/docs) 与 Marketplace 页面为准。

## 先建立配置边界

VS Code 有三个常用配置层级：

| 层级 | 适合放什么 | 是否提交到仓库 |
| --- | --- | --- |
| User Settings | 字体、主题、通用编辑习惯 | 否，可用 Settings Sync 同步 |
| Workspace Settings | 编译数据库、格式化器、项目搜索排除项 | 是，通常位于 `.vscode/settings.json` |
| Profiles | 不同技术栈的扩展和界面组合 | 按个人需要导出 |

可以把边界概括为一句话：**个人偏好放用户配置，影响构建和协作一致性的设置放工作区。** 本机绝对路径、密钥，以及只在当前电脑存在的解释器位置，都不应该提交到仓库。

团队还可以在 `.vscode/extensions.json` 中记录推荐扩展，让新成员打开项目时获得明确提示，而不是依赖口头清单：

```json
{
  "recommendations": [
    "ms-vscode.cpptools",
    "ms-vscode.cmake-tools",
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.debugpy"
  ]
}
```

“推荐”并不等于强制安装；它只是把项目依赖的编辑器能力写进版本控制。

## C/C++ 与 CMake

### 基础扩展

- [C/C++](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools)：IntelliSense、调试、代码导航和 clang-format 接入；
- [CMake Tools](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cmake-tools)：配置、构建、选择 Kit、运行目标和 CTest；
- [C/C++ Extension Pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools-extension-pack)：用于一次安装微软维护的常用组合；如果已经单独安装前两项，就不必再装扩展包。

对 CMake 项目，优先让 CMake Tools 向 C/C++ 扩展提供编译信息：

```json
{
  "C_Cpp.default.configurationProvider": "ms-vscode.cmake-tools",
  "cmake.configureOnOpen": false,
  "cmake.buildDirectory": "${workspaceFolder}/build"
}
```

`configurationProvider` 会把真实的宏、头文件路径和编译选项交给语言服务，比手工维护一长串 `includePath` 更可靠。大型项目也可以生成 `compile_commands.json`，让编辑器看到的编译上下文与实际构建保持一致。

### 格式化与诊断

C/C++ 扩展可以调用 clang-format。建议把风格写进仓库根目录的 `.clang-format`，而不是每位开发者各自调整：

```json
{
  "[c]": {
    "editor.defaultFormatter": "ms-vscode.cpptools",
    "editor.formatOnSave": true
  },
  "[cpp]": {
    "editor.defaultFormatter": "ms-vscode.cpptools",
    "editor.formatOnSave": true
  }
}
```

静态分析工具应由项目任务或构建脚本显式运行。编辑器诊断负责快速反馈，CI 则负责执行团队统一的最终检查；两者职责不同，不能互相替代。

## Python

### 核心扩展

- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)：环境选择、测试、运行和项目入口；
- [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)：类型分析、补全与代码导航；
- [Python Debugger](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy)：基于 debugpy 的调试能力。

Python 项目通常把虚拟环境放在仓库根目录的 `.venv` 中。这个目录不应提交，但固定的目录名可以让开发者和编辑器更容易发现环境：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell 中的激活命令是：

```powershell
.venv\Scripts\Activate.ps1
```

创建环境后，从命令面板运行 `Python: Select Interpreter`，选择当前工作区的 `.venv`。不要提交某台电脑上的完整解释器路径；VS Code 会为工作区记住选择。需要基础类型检查时，可以保留下面这项工作区设置：

```json
{
  "python.analysis.typeCheckingMode": "basic"
}
```

格式化与 lint 工具应根据项目统一选择，例如 Ruff、Black 或其他团队标准。不要同时启用多个会修改同一文件的格式化器，否则一次保存可能触发相互覆盖的修改。

## Remote SSH

[Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 让本地 VS Code 界面连接远程主机，并把语言服务、终端和项目进程运行在远端。它适合依赖 Linux 工具链、GPU 服务器或内网开发机的场景。

先把连接信息放进标准 SSH 配置，而不是散落在 VS Code 设置中：

```text
Host gpu-dev
    HostName 192.0.2.10
    User developer
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
```

然后从命令面板执行 `Remote-SSH: Connect to Host...`，选择 `gpu-dev`。

远程开发最容易混淆的是“界面在本地，项目环境在远端”。需要特别注意：

- 扩展可能分为“本地安装”和“远端安装”，语言服务通常应装在远端；
- Git 凭据、编译器和 Python 环境属于远程主机，不会自动从本机复制；
- 密钥应由 SSH agent 或系统密钥链管理，不要写进工作区配置；
- 网络不稳定时先检查原生 `ssh gpu-dev`，再排查 VS Code。

更完整的连接限制与排错方式见 [Remote Development using SSH](https://code.visualstudio.com/docs/remote/ssh)。

## 通用编辑设置

下面这组用户配置强调基础一致性，不绑定特定主题或字体：

```json
{
  "editor.formatOnSave": true,
  "editor.rulers": [100],
  "editor.renderWhitespace": "selection",
  "editor.bracketPairColorization.enabled": true,
  "files.trimTrailingWhitespace": true,
  "files.insertFinalNewline": true,
  "files.autoSave": "off",
  "terminal.integrated.scrollback": 10000,
  "workbench.startupEditor": "none"
}
```

`formatOnSave` 只有在每种语言都指定了唯一格式化器时才真正稳定。团队项目还应配合 EditorConfig、`.clang-format`、`pyproject.toml` 等仓库级配置；编辑器设置负责调用工具，风格规则本身应尽量由项目文件定义。

## 可选扩展

以下扩展有价值，但不属于语言工具链的基础依赖：

- [Error Lens](https://marketplace.visualstudio.com/items?itemName=usernamehw.errorlens)：把诊断信息显示在代码行附近；
- [GitLens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens)：增强 blame、提交历史和分支信息；
- [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)：在容器中建立可复现开发环境；
- 主题与图标扩展：只影响视觉，可按个人偏好选择。

Code Runner 这类“一键运行当前文件”的扩展适合临时代码片段，但不应代替项目真实的构建、测试和调试命令。CMake、CTest、pytest 或仓库脚本才是其他开发者和 CI 能够复现的入口。

AI 补全扩展也应单独评估代码上传策略、许可、企业合规和资源占用，而不是作为所有项目的默认依赖。

## 配置完成后的验收

安装扩展和复制设置只是开始。至少检查下面几条，才能确认环境真正可用：

- 打开一个源码文件，确认跳转定义、补全和诊断来自正确的项目环境；
- 执行一次真实构建，而不是只运行当前文件；
- 从编辑器运行一个测试，并确认命令与 CI 使用的入口一致；
- 修改并保存文件，确认只有预期的格式化器生效；
- 远程项目中确认终端、语言服务和调试目标都位于远程主机；
- 重新克隆到临时目录，按照仓库说明验证环境能够重建。

如果其中任何一步依赖手工填写的本机路径，说明配置还没有真正做到可迁移。

## 一套精简的配置顺序

1. 先安装语言官方扩展，确认补全、跳转和调试正常；
2. 再接入项目构建系统，例如 CMake Tools；
3. 把格式化、lint、测试入口和扩展建议写进仓库；
4. 确有远程需求时再安装 Remote - SSH 或 Dev Containers；
5. 最后添加主题、Git 增强和诊断展示类扩展。

每增加一个扩展，都应该能回答“它解决了哪个现有问题”。如果功能与另一扩展重叠、长期不使用，或显著拖慢启动和索引，就应该移除。

## 总结

好的 VS Code 配置不是一张越长越好的扩展清单，而是一套能够解释、迁移和验证的工作流。让语言扩展负责代码理解，让构建工具负责真实命令，让仓库配置负责团队一致性；个人主题和快捷键则留在用户设置中。这样无论是换电脑、进入容器还是连接远程主机，开发环境都能沿着同一条路径恢复。
