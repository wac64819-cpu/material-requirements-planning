# v0.7 前端回归验证 — 2026-10-26

## 结果

在本机 Microsoft Edge 无界面浏览器和真实 Python HTTP 服务上执行，使用独立临时 SQLite 数据库。所有套件成功结束，合计105项断言通过。这是浏览器检查数量，场景可能重叠，不代表105个独立业务需求。

| 套件 | 通过 | 主要覆盖 |
|---|---:|---|
| 工作台 | 30/30 | 计算、优先级、四表增删、错误定位、安全整数、采购余量、日期风险、旧响应丢弃、断网重试、390px |
| 保存与历史 | 14/14 | 编辑保存、刷新恢复、跨页面版本冲突、历史输入快照、非法保存阻断、服务重启恢复 |
| CSV | 37/37 | 下载模板、导入预览/应用/保存、无效表头/编码、五种真实下载文件内容、空风险表与非空风险表 |
| 分区导航 | 24/24 | 三分区可见性、高亮及焦点、未保存编辑保留、历史加载取消与失败重试、旧失败响应保护、390px三分区及历史按钮 |

证据：[工作台](workbench-verification.json)、[保存与历史](persistence-ui-verification.json)、[CSV](csv-ui-verification.json)、[导航](navigation-ui-verification.json)、[汇总与文件指纹](summary.json)。

## 发现并修复的问题

历史计划尚在加载时切换分区，会使请求结果失效，但原代码没有清除“正在读取计划…”提示。返回历史页后，提示会一直留着。

新增测试先复现失败，证据保存在 [修复前记录](navigation-before-fix.json)。修复后切换分区会清除旧提示；历史请求的失败处理也检查请求版本，防止较早请求的失败信息覆盖较新的成功状态。导航套件最终24项全部通过。

改动位于 `web/app.js` 的导航事件处理和 `viewHistory` 失败处理，未修改物料需求算法、库存分配规则或数据库结构。

## 导出内容验证

- 生产计划：4行，检查已保存批次编号与独立预期生产数量。
- 采购计划：4行，逐项核对物料、需要日期、采购量、下单日期。
- 库存分配：8行，核对HIGH任务的B库存20 → 分配20 → 剩余0。
- 来源追溯：8行，核对HIGH任务D的路径A → B → D，以及贡献400、抵扣100、剩余300。
- 风险表：无风险时保留完整表头；另造30天生产提前期的案例，检查HIGH任务A的建议开始日期2026-09-21，早于基准日10天。

实际下载文件以 `download-*.csv` 保存。上述数量属于CSV测试中HIGH=60的独立示例，不应与默认HIGH=50示例混用。

## 视觉检查

已打开检查390px基础数据、计划计算和历史记录截图；表格在容器内横向滚动，页面本身不出现整体横向溢出。测试实际点击窄屏历史表中的“查看”，并再次计算和显示导出入口。

- [基础数据](navigation-mobile-data.png)
- [计划计算](navigation-mobile-planning.png)
- [历史记录](navigation-mobile-history.png)
- [重新计算结果](navigation-mobile-result.png)

## 复现

在 `material-planning` 目录下运行以下PowerShell命令。需要Node.js、Microsoft Edge，以及脚本中配置的Python与Playwright依赖。每个脚本创建独立临时数据库；保存与历史脚本会先调用工作台脚本，所以无需另跑工作台。

```powershell
$env:MRP_TEST_ARTIFACT_DIR = Join-Path (Get-Location) 'results\ui-regression-new-run'
node verify_persistence_ui.cjs
node verify_csv_ui.cjs
node verify_navigation_ui.cjs
```

三条命令必须分别确认退出码为0，再检查各JSON结果；不能仅根据输出目录存在就判定通过。`MRP_TEST_ARTIFACT_DIR` 会把新报告和截图写入独立目录；不设置时沿用脚本的历史默认输出位置。

## 范围

本轮完成的是前端回归及针对性修复。原有E4、E5技术报告和证据保留原版本；没有声称重新执行全部125条HTTP黑盒用例或性能测试。搜索分页、下拉录入、BOM树和计算过程讲解仍属于后续功能优化。
