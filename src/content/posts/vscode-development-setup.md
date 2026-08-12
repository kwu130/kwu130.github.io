---
title: "VS Code 开发环境配置：C/C++、Python 与远程开发"
description: "用一组职责清晰的扩展和少量可迁移设置，搭建适合 C/C++、Python、CMake 与 Remote SSH 的开发环境。"
publishedAt: 2024-07-01
updatedAt: 2026-08-13
tags:
  - "开发工具"
  - "VS Code"
slug: "vscode-development-setup"
legacyPaths:
  - "/post/vscode-cha-jian-he-kai-fa-she-zhi.html"
issueNumber: 2
draft: false
---

VS Code 的扩展很多，但“安装得多”并不等于“开发体验更好”。一个稳定配置应该满足三个条件：每个扩展职责明确、项目配置可以进入版本控制、离开当前电脑后仍容易重建。

下面是一套偏克制的配置，覆盖 C/C++、Python、CMake 和远程 Linux 开发。扩展名称和设置可能随版本调整，安装前应以 [VS Code 官方文档](https://code.visualstudio.com/docs) 与 Marketplace 页面为准。

## 先建立配置边界

VS Code 有三个常用配置层级：

| 层级 | 适合放什么 | 是否提交到仓库 |
| --- | --- | --- |
| User Settings | 字体、主题、通用编辑习惯 | 否，可用 Settings Sync 同步 |
| Workspace Settings | 编译数据库、格式化器、项目搜索排除项 | 是，通常位于 `.vscode/settings.json` |
| Profiles | 不同技术栈的扩展和界面组合 | 按个人需要导出 |

原则是：**个人审美放用户配置，影响项目一致性的设置放工作区。** 不要把本机绝对路径、密钥或只在自己电脑存在的解释器路径提交到仓库。

## C/C++ 与 CMake

### 必需扩展

- [C/C++](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools)：IntelliSense、调试、代码导航和 clang-format 接入；
- [CMake Tools](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cmake-tools)：配置、构建、选择 Kit、运行目标和 CTest；
- [C/C++ Extension Pack](https://marketplace.visualstudio.com/items?itemName=ms-vscode.cpptools-extension-pack)：如果希望一次安装微软维护的常用组合，可以使用扩展包；已经单独安装时不必重复。

对 CMake 项目，优先让 CMake Tools 向 C/C++ 扩展提供编译信息：

```json
{
  "C_Cpp.default.configurationProvider": "ms-vscode.cmake-tools",
  "cmake.configureOnOpen": false,
  "cmake.buildDirectory": "${workspaceFolder}/build"
}
```

`configurationProvider` 能提供真实的宏、头文件路径和编译选项，比手工维护很长的 `includePath` 更可靠。大型项目也可以生成 `compile_commands.json`，让编辑器与实际构建保持一致。

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

静态分析工具应由项目构建或任务显式运行。编辑器诊断适合快速反馈，但 CI 才是最终一致性边界。

## Python

### 核心扩展

- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)：环境选择、测试、运行和项目入口；
- [Pylance](https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance)：类型分析、补全与代码导航；
- [Python Debugger](https://marketplace.visualstudio.com/items?itemName=ms-python.debugpy)：基于 debugpy 的调试能力。

Python 项目应在仓库内使用虚拟环境，并让解释器选择保持可预测：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

工作区设置可以提供默认位置，同时保留用户手动切换解释器的能力：

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.analysis.typeCheckingMode": "basic"
}
```

格式化与 lint 工具应根据项目选择，例如 Ruff、Black 或其他团队标准。不要同时启用多个会修改同一文件的格式化器，否则保存时可能互相覆盖。

## Remote SSH

[Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 允许本地 VS Code 界面连接远程主机，并把大部分语言服务运行在远端。它适合需要 Linux 编译环境、GPU 服务器或内网开发机的场景。

先把连接信息放进标准 SSH 配置，而不是散落在 VS Code 设置中：

```text
Host gpu-dev
    HostName 192.0.2.10
    User developer
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 60
```

然后从命令面板执行 `Remote-SSH: Connect to Host...`，选择 `gpu-dev`。

远程开发需要注意：

- 扩展可能分为“本地安装”和“远端安装”，语言服务通常应装在远端；
- Git 凭据、编译器和 Python 环境属于远程主机，不会自动从本机复制；
- 密钥应由 SSH agent 或系统密钥链管理，不要写进工作区配置；
- 网络不稳定时先检查原生 `ssh gpu-dev`，再排查 VS Code。

更完整的连接限制与排错方式见 [Remote Development using SSH](https://code.visualstudio.com/docs/remote/ssh)。

## 通用编辑设置

下面的用户配置强调一致性，不绑定特定主题或字体：

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

`formatOnSave` 只有在语言已经指定唯一格式化器时才真正稳定。团队项目还应配合 EditorConfig、clang-format、pyproject.toml 等仓库级配置。

## 可选扩展

以下扩展有价值，但不属于语言工具链的必需部分：

- [Error Lens](https://marketplace.visualstudio.com/items?itemName=usernamehw.errorlens)：把诊断信息显示在代码行附近；
- [GitLens](https://marketplace.visualstudio.com/items?itemName=eamodio.gitlens)：增强 blame、提交历史和分支信息；
- [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)：在容器中建立可复现开发环境；
- 主题与图标扩展：只影响视觉，可按个人偏好选择。

像 Code Runner 这类“一键运行当前文件”的扩展适合小片段，但不应代替项目真实的构建、测试和调试命令。CMake、CTest、pytest 或仓库脚本才是可复现入口。

AI 补全扩展也应单独评估代码上传策略、许可、企业合规和资源占用，而不是作为所有项目的默认依赖。

## 一套精简的安装顺序

1. 先安装语言官方扩展，确认补全、跳转和调试正常；
2. 再接入项目构建系统，例如 CMake Tools；
3. 把格式化、lint 和测试规则写进仓库；
4. 确有远程需求时安装 Remote - SSH 或 Dev Containers；
5. 最后才添加主题、Git 增强和诊断展示类扩展。

每增加一个扩展，都应该能回答“它解决了哪个现有问题”。如果功能与另一扩展重叠、长期不使用，或显著拖慢启动和索引，就应该移除。

## 总结

好的 VS Code 配置不是一张越长越好的扩展清单，而是一套能解释、能迁移、能复现的工作流。让官方语言扩展负责语义能力，让构建工具负责真实命令，让仓库配置负责团队一致性；个人主题和快捷键则留在用户设置里。这样换电脑、进容器或连接远程主机时，环境都更容易恢复。
