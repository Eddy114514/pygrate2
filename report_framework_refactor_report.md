# report_framework 重构报告

## 1. 最终目标架构

- 后端保留 Flask，入口仍是 `report_framework/web_frontend.py`，但职责已经收口为 app factory + blueprint 注册。
- 前端迁移到 `report_framework/frontend/`，使用 Vite + React 18 + Ant Design 5 + CodeMirror 6。
- 页面主路径收口为一个 workspace shell：
  - `/project` 打开项目
  - `/` 进入统一工作区
  - `/diff` 保留为 legacy fallback
- warning / proposal / warningId / diff / save baseline 的 source of truth 保持在后端。
- 规则系统从弱类型 dict 收口为 typed `WarningRule` dataclass，保留现有行为，不急着扩新 rule。

## 2. 改了哪些文件

### 前端工程化
- `report_framework/frontend/package.json`
- `report_framework/frontend/package-lock.json`
- `report_framework/frontend/vite.config.js`
- `report_framework/frontend/.gitignore`
- `report_framework/frontend/src/main.jsx`
- `report_framework/frontend/src/app/AppShell.jsx`
- `report_framework/frontend/src/app/routes.jsx`
- `report_framework/frontend/src/api/client.js`
- `report_framework/frontend/src/api/types.js`
- `report_framework/frontend/src/features/project/ProjectPage.jsx`
- `report_framework/frontend/src/features/workspace/WorkspacePage.jsx`
- `report_framework/frontend/src/features/workspace/useWorkspaceState.js`
- `report_framework/frontend/src/features/workspace/usePreviewApply.js`
- `report_framework/frontend/src/features/workspace/useSaveAndReanalyze.js`
- `report_framework/frontend/src/features/editor/useWarningDecorations.js`
- `report_framework/frontend/src/components/*`
- `report_framework/frontend/src/styles/theme.js`
- `report_framework/frontend/src/styles/global.css`

### 后端服务化 / 路由收口
- `report_framework/web_frontend.py`
- `report_framework/routes/api_routes.py`
- `report_framework/routes/page_routes.py`
- `report_framework/services/file_service.py`
- `report_framework/services/analysis_service.py`
- `report_framework/services/warning_payload_service.py`
- `report_framework/services/history_service.py`
- `report_framework/services/diff_service.py`
- `report_framework/services/frontend_asset_service.py`
- `report_framework/templates/frontend_shell.html`

### 规则系统 / 核心逻辑
- `report_framework/models/rule_models.py`
- `report_framework/warning_fixes.py`
- `report_framework/framework.py`
- `report_framework/apply_engine.py`

### 测试 / legacy 标注
- `report_framework/test_apply_engine.py`
- `report_framework/test_apply_cmp_method.py`
- `report_framework/static/editor_app.js`
- `report_framework/static/project_app.js`
- `report_framework/templates/report.html`
- `report_framework/templates/project.html`
- `report_framework/templates/diff.html`

## 3. 新的前端目录结构

```text
report_framework/frontend/
  .gitignore
  package.json
  package-lock.json
  vite.config.js
  src/
    main.jsx
    app/
      AppShell.jsx
      routes.jsx
    api/
      client.js
      types.js
    features/
      editor/
        useWarningDecorations.js
      project/
        ProjectPage.jsx
      workspace/
        WorkspacePage.jsx
        usePreviewApply.js
        useSaveAndReanalyze.js
        useWorkspaceState.js
    components/
      DiffPanel.jsx
      EditorPane.jsx
      FileTree.jsx
      OutputPanel.jsx
      StatusBar.jsx
      Toolbar.jsx
      WarningDetails.jsx
      WarningTable.jsx
    styles/
      global.css
      theme.js
```

说明：
- 不再依赖浏览器内 Babel、全局 React、jQuery、jsTree。
- Vite build 输出到 `report_framework/static/frontend/`，Flask 通过 manifest 读取静态资源。
- 可选开发模式：设置 `PYGRATE_VITE_DEV_SERVER=http://127.0.0.1:5173` 后，Flask 页面会改为加载 Vite dev server。

## 4. 新的后端目录结构 / service 划分

```text
report_framework/
  web_frontend.py
  apply_engine.py
  framework.py
  warning_fixes.py
  models/
    rule_models.py
  routes/
    api_routes.py
    page_routes.py
  services/
    analysis_service.py
    diff_service.py
    file_service.py
    frontend_asset_service.py
    history_service.py
    warning_payload_service.py
```

职责划分：
- `web_frontend.py`：app factory，注册 blueprint，兼容导出 warning serialization helper 供老测试复用。
- `routes/api_routes.py`：JSON API，只负责 request/response。
- `routes/page_routes.py`：页面路由，只负责 shell / legacy 页面渲染。
- `services/analysis_service.py`：项目状态与单文件分析聚合。
- `services/warning_payload_service.py`：warning payload 序列化与稳定 `warningId`。
- `services/history_service.py`：保存与 baseline refresh。
- `services/diff_service.py`：统一 diff 读取与统计。
- `services/file_service.py`：项目树、文件读取。

已处理的原型问题：
- 已去掉 `from file_io import *`
- 已去掉 `CURRENT_PROJECT_ROOT` 这类主要全局状态
- `web_frontend.py` 不再同时承担路由、序列化、保存、diff、项目树构建

## 5. UI 升级点（逐项说明）

### 项目打开页
- 改成居中 `Card` + `Form`。
- 支持最近项目路径缓存到 `localStorage`。
- 右侧大空白被收掉，页面有明确标题和说明文案。
- 文件预览树改成 Ant Design `Tree`，不再用 jsTree。

### Workspace 主界面
- 收口为单一工作区：左树、中编、右检、底部 output/diff。
- 顶部统一工具栏：
  - Analyze
  - Save
  - Preview Apply
  - Fix Selected
  - Fix All
  - Reanalyze
  - View Diff
- 顶部同时展示 engine root、project root、当前文件、warning 数、auto-fixable 数、dirty 状态、最近分析时间。

### 编辑器
- CodeMirror 5 替换为 CodeMirror 6。
- warning 高亮与 gutter marker 统一在 `useWarningDecorations.js`。
- 选中 warning 会滚动定位。
- warning span 高亮优先使用精确 `colStart/colEnd`。

### Warnings + Details
- 警告列表改成 AntD `Table`。
- type 用 `Tag`，auto-fixable 一眼可见。
- 右侧详情用 `Card + Descriptions`。
- `CMP_METHOD_WARNING` 会显示 `resolutionStatus` / `resolutionDetails`，不再只是裸 message。

### Output + Diff
- Output 和 Diff 收到工作区底部 `Tabs`。
- 预览 diff 和已保存 diff 不再必须跳独立页面才能看。
- `/diff` 页仍保留，但已经退居 fallback。

### 空态 / 错误态 / 加载态
- 未选文件、无 warning、无 diff、analyze error、preview/save error 都有明确 `Empty` / `Alert` 呈现。

## 6. 交互流变化（打开项目 / 分析 / 选中 warning / preview apply / save+reanalyze / diff）

### 打开项目
1. 访问 `/project`
2. 在 AntD `Form` 输入 engine root / project root
3. 点击 `Open Workspace`
4. 跳转到 `/?engine=...&root=...`

### 分析文件
1. 在左侧树中点文件
2. 前端调用 `/api/analyze_file`
3. 后端 `analysis_service.analyze_workspace()` 聚合：
   - `framework.analyze_file_with_output()`
   - `warning_payload_service.serialize_warnings_for_client()`
4. 工作区刷新 source、warnings、run output

### 选中 warning
1. 在右侧表格点击 warning，或在编辑器高亮区域点击
2. 前端只维护 `selectedWarningId`
3. 详情面板与编辑器定位同步更新

### Preview Apply
1. 点击 `Apply this fix` / `Fix Selected` / `Fix All`
2. 前端调用 `/preview_apply`
3. 后端 `apply_engine.apply_fix_proposals()`：
   - 应用 `SourceEdit`
   - 自动补 import
   - 生成 unified diff
4. 返回新的 `sourceText + diffText`
5. 编辑器与底部 Preview Diff 同步更新

### Save + Reanalyze
1. 点击 `Save`
2. 前端调用 `/save_and_reanalyze`
3. 后端：
   - `history_service.save_source_text()`
   - `analysis_service.analyze_workspace()`
4. 前端刷新：
   - 保存后的源码
   - 新 warning 列表
   - output
   - warning count

### Diff
- 工作区底部 `Saved Diff` tab 通过 `/api/diff` 加载。
- `/diff` fallback 页面仍可打开，但主路径已经迁到 workspace 内。

## 7. 删除或替换了哪些“自己造轮子”的部分

已替换：
- jQuery + jsTree -> Ant Design `Tree`
- 浏览器内 Babel -> Vite build
- 全局 React app -> 真实模块化 React 前端
- 零散 fetch -> `frontend/src/api/client.js`
- CodeMirror 5 旧页面集成 -> CodeMirror 6 + hook 化 decorations

保留且应保留的自定义逻辑：
- runtime warning 解析
- `CMP_METHOD_WARNING` callsite 反解
- `SourceEdit` / `FixProposal` / preview apply pipeline
- Py2 -> Py3 warning-specific rewrite logic

## 8. 重复代码清理了哪些

- warning payload 序列化统一到 `services/warning_payload_service.py`
- warningId 生成统一到后端 helper，不再由前端拼
- diff 构建统一由 `apply_engine.build_unified_diff()` 提供，`diff_service` 和 preview apply 共用
- save / autosave / save_and_reanalyze 共用 `history_service.save_source_text()`
- 项目树构建统一到 `services/file_service.py`
- page 路由和 API 路由拆开，不再堆在 `web_frontend.py`

## 9. 规则系统做了什么重构

- 新增 typed rule model：`models/rule_models.py`
- `WarningRule` 字段统一为：
  - `name`
  - `warning_type`
  - `message_match`
  - `fix_scope`
  - `highlight_mode`
  - `fix_kind`
  - `pattern`
  - `replacement`
  - `replacement_func`
  - `imports`
  - `regex_grade`
  - `notes`
- `warning_fixes.py` 不再主要依赖 magic string dict
- `viewkeys/viewvalues/viewitems` 和 `iterkeys/itervalues/iteritems` 改为 `method_rename_rule(...)` 工厂生成
- 现有行为基本不变，仍由 `framework._enrich_with_rule()` 驱动

## 10. regex 审查结果（A/B/C 分级）

### A 类：可以继续 regex / 低风险
- `dict.viewkeys/viewvalues/viewitems` -> `keys/values/items`
- `dict.iterkeys/itervalues/iteritems` -> `keys/values/items`
- `buffer(...)` -> `memoryview(...)`
- `BytesIO.truncate(0)`：
  - 实际不是纯 regex，已用 callable + parso 风格解析
  - 当前属于较稳的结构化修正

### B 类：短期保留，但需要清楚知道限制
- `print_statement`
  - 复杂 `print >>`、尾逗号等形式仍脆弱
- `file_constructor`
  - 当前只是 presentation-only，没有 backend auto-fix
- `tokenize_behavior`
  - 仅展示，无 auto-fix
- `base64_b16/b32/b64encode`
  - 仅展示，无 auto-fix

### C 类：明显脆弱，后续应该优先升级
- `dict_has_key`
  - 当前仍靠 regex，复杂 receiver / 嵌套调用不够稳
- `cmp_argument`
  - 当前 `cmp=` -> `key=cmp_to_key(...)` 仍靠 regex
  - multiline kwargs、嵌套表达式、lambda / 复杂右值后续应优先升级为结构化匹配

结论：
- 这次先完成 typed 化和分级，不盲目把所有 regex 一次性替换掉。
- 后续最值得优先升级的是 `cmp_argument` 和 `dict_has_key`。

## 11. 测试与验证结果

### 后端测试
执行：

```bash
python3 -m unittest discover -s report_framework -p 'test_apply*.py'
```

结果：

```text
....................
----------------------------------------------------------------------
Ran 20 tests in 0.155s

OK
```

覆盖：
- apply engine
- preview apply
- save_and_reanalyze
- warningId 稳定性
- `/autosave`
- `/api/project` 树结构
- `/project` shell 渲染
- `CMP_METHOD_WARNING` 专项诊断

### Python 编译检查

执行：

```bash
python3 -m py_compile \
  report_framework/web_frontend.py \
  report_framework/routes/api_routes.py \
  report_framework/routes/page_routes.py \
  report_framework/services/file_service.py \
  report_framework/services/warning_payload_service.py \
  report_framework/services/analysis_service.py \
  report_framework/services/history_service.py \
  report_framework/services/diff_service.py \
  report_framework/services/frontend_asset_service.py \
  report_framework/models/rule_models.py \
  report_framework/warning_fixes.py \
  report_framework/framework.py \
  report_framework/test_apply_engine.py \
  report_framework/test_apply_cmp_method.py
```

结果：通过。

### 前端构建

执行：

```bash
cd report_framework/frontend
npm install
npm run build
```

结果：
- Vite build 成功
- 输出生成到 `report_framework/static/frontend/`
- 仍有 Ant Design vendor chunk 偏大的 warning，但不影响功能闭环

## 12. 仍然存在的限制

- `CMP_METHOD_WARNING` 仍未实现 auto-fix，只保留检测 / 定位 / resolution quality 展示
- 还没有目录级批量 analyze / preview / save / reanalyze
- `/diff` fallback 页面仍是 legacy 页面，没有完全并入 React workspace
- 旧模板和旧 JS 仍保留在仓库里，但已经明确标注为 legacy
- 前端还没有单元测试；这次用的是 `vite build + Flask route smoke + backend unittest`
- Ant Design 打包体积较大，后续如果继续膨胀，建议再做 route-level code splitting

## 13. 下一步建议

1. 优先把 `cmp_argument` 和 `dict_has_key` 从 regex 升级为结构化匹配
2. 给 React 前端补最少量 smoke tests
   - warning selection
   - save+reanalyze 状态保持
   - preview diff 更新
3. 再决定是否把 `/diff` fallback 页面完全移除
4. 最后再做第一个 semantic refactor demo
   - 不建议在 UI 仍不稳定前先冲 `CMP_METHOD_WARNING` auto-fix

### 给 ChatGPT 的审阅摘要
- 当前是否已完成 Vite + React + AntD 迁移：已完成主路径迁移，并已通过 `npm run build`
- 文件树是否已移除 jsTree：主路径已移除，AntD Tree 已接管；旧 jsTree 文件仍保留但已标注 legacy
- Workspace 是否已统一为左树中编右检底部输出/diff：已完成
- 后端是否已去除 star import / 主要全局状态：是；`CURRENT_PROJECT_ROOT` 已去掉，未发现 `* import`
- 规则系统是否已 typed 化：是，已引入 `WarningRule` dataclass 和工厂化 rename rules
- 哪些 regex 仍然脆弱：`dict_has_key`、`cmp_argument` 最脆；`print_statement` 次之
- 目前最大的未完成项：前端测试仍缺，`CMP_METHOD_WARNING` auto-fix 仍未做
- 建议下一步先 review 哪些文件：`report_framework/frontend/src/features/workspace/WorkspacePage.jsx`、`report_framework/services/warning_payload_service.py`、`report_framework/warning_fixes.py`、`report_framework/framework.py`

## 手动验收清单

### 启动
1. 安装前端依赖：
   ```bash
   cd /home/cmu/pygrate2/report_framework/frontend
   npm install
   npm run build
   ```
2. 启动 Flask：
   ```bash
   cd /home/cmu/pygrate2
   python3 report_framework/web_frontend.py --port 5000
   ```
3. 打开：
   ```text
   http://127.0.0.1:5000/project
   ```

### 打开项目
1. 在项目页输入：
   - engine root: `/home/cmu/pygrate2`
   - project root: `/home/cmu/pygrate2/report_framework/test`
2. 点击 `Open Workspace`
3. 确认进入统一 workspace，而不是旧版 editor/report 页面

### 选择文件与 Analyze
1. 在左侧树选择 `test_scripte.py`
2. 确认中间编辑器加载源码
3. 点击 `Analyze` 或 `Reanalyze`
4. 确认右侧 warning 列表出现

### 查看 warning 详情
1. 点击 warning 表格中的某一条
2. 确认：
   - 编辑器滚动定位
   - 高亮 span 与 warning 对齐
   - 右侧 details 面板同步更新

### Preview apply
1. 选一条 `CMP_ARG_WARNING` / `HAS_KEY_WARNING` / `BYTESIO_TRUNCATE_WARNING`
2. 点击 `Apply this fix` 或顶部 `Fix Selected`
3. 确认：
   - 编辑器文本更新
   - 底部 `Preview Diff` tab 出现 diff
   - 需要时自动补 import

### Save + reanalyze
1. 点击 `Save`
2. 确认：
   - 文件实际写回磁盘
   - warning 列表自动刷新
   - warning 数下降
   - output 区同步更新

### 查看 diff
1. 点击顶部 `View Diff`
2. 确认底部 `Saved Diff` 有内容
3. 如需 fallback，再访问：
   ```text
   http://127.0.0.1:5000/diff?root=/home/cmu/pygrate2/report_framework/test&file=test_scripte.py
   ```

### CMP_METHOD_WARNING 定位
1. 在 `test_scripte.py` 中定位 `CMP_METHOD_WARNING`
2. 点击 warning
3. 确认：
   - 仍可正确跳到 caller site
   - details 面板能看到 `resolutionStatus`
   - 尚无 auto-fix 按钮生效，这是当前已知范围
