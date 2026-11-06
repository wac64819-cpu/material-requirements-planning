# 物料计划工作台 v0.7

已串通：输入校验 → 多层 BOM → 按任务优先级共享库存 → 按日期采购与余量 → 日期风险。Python 标准库、过程式函数，没有自定义类。

**现在可以直接操作：[本地工作台](http://127.0.0.1:8765)。** 首次使用请双击本目录的“启动工作台.cmd”，它会启动服务并打开浏览器；保留启动窗口，关闭窗口即停止服务。若服务已运行，直接访问链接即可。也可运行 `python web_server.py` 后手动打开链接。

界面采用深蓝灰背景、青色操作按钮和分区导航。基础数据页编辑物料、BOM、库存和任务，并展示实际记录数量；计划计算页选择任务、生成计划和导出结果；历史记录页查看已保存的计划。桌面使用侧栏，窄屏使用顶部导航。切换分区保留当前编辑，校验问题可定位到原字段。[新版界面与验证说明](results/dark-ui-review.md)记录本次变更；[原操作说明](../specs/material-requirements-planning/workbench-v0.3.md)中的业务步骤仍适用，但旧版页面位置以新版为准。

点击“保存数据”后，刷新或重启会恢复最近保存的数据及任务选择。未点击保存的新编辑仍会在离开页面后丢失。首次使用没有已保存数据时载入示例；载入示例不会自动覆盖数据库。

每次成功“生成计划”都会保存独立批次，在“历史记录”分区点击“查看”会进入计划计算页，显示当时的输入快照、生产采购结果及库存/来源明细。查看历史不会替换正在编辑的数据，修改新数据不会改变旧计划。计算并保存历史不等于保存当前编辑工作区，两者按钮职责不同。

本地SQLite数据位于 `data/planning.sqlite3`，无需安装数据库服务。保存失败不会返回成功；两个页面同时编辑时，较旧页面保存会提示冲突，防止覆盖。详见 [保存与历史说明](../specs/material-requirements-planning/persistence-v0.4.md)。

原有 [三个静态计算示例](results/demo-plans.html) 继续保留，可在不开服务时查看。

## CSV导入导出

展开基础数据下方“从CSV导入数据”，下载模板，选择需要替换的一张或多张表，依次点击“校验所选文件”“应用并替换所选表”。失败时不改原数据；应用后仍需“保存数据”，才会保留到下次打开。新导入的任务请核对勾选。

成功计算或查看历史后，在结果区选择生产计划、采购与余量、库存分配、需求来源或交期风险，再点“下载CSV”。导出读取该计划的已保存快照，不受当前编辑影响。

[下载四表示例模板](results/mrp-csv-templates.zip) · [CSV字段与使用说明](../specs/material-requirements-planning/csv-v0.5.md)

## 运行

在本目录执行（Python 3）：

```powershell
python run_plan.py
python run_plan.py sample-input.json
python verify_planner.py
python verify_core.py
python verify_performance.py
```

若电脑未配置 Python 命令，本机可直接使用：

```powershell
& 'C:\Users\许yq\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'C:\Users\许yq\Desktop\软件工程\material-planning\run_plan.py'
```

sample-input.json 含 sources 和 request，可修改副本后传入。默认生成 results/demo-plans.html 和 .json；自定义输入生成 results/custom-plan.html 和 .json。重跑会覆盖对应演示输出，不是历史批次存储。有效计划退出码为 0，阻断错误为 1，文件读取/格式问题为 2。

## 已实现

- 多层 BOM 与循环检查，缺失引用/库存、非法数量及日期的错误定位。
- 任务优先级先于交期；共享组件先收齐上层需求，再按需要日期分配库存。
- 成品和半成品先抵库存，只展开净生产量；保留 BOM 路径和父需求关联。
- 同日采购缺口合并，最小量/倍数取整，早期计划余量抵扣后续需求。
- 日历日逐层倒推，基准日前日期保留并标风险。
- 输入快照和结果关联；输入不变、重算不沿用临时库存和余量。

planner.py 为计算流程，core.py 为原有四个叶子函数；run_plan.py 为新演示入口。run_demo.py 保留为旧的叶子函数示例。

## 验证与限制

2026-10-26 已补齐 v0.7 完整前端回归：工作台30/30、保存与历史14/14、CSV37/37、分区导航24/24，共105项浏览器断言通过。覆盖390px三个分区、断网重试、过期结果丢弃、五种CSV内容、保存冲突和服务重启。修复历史请求取消后提示残留，以及旧失败请求干扰新状态的问题。见 [本次验证报告](results/ui-regression-2026-10-26/README.md)。原始 E4/E5 证据未被本次结果覆盖，以下既有数字仍对应各自历史执行日期。

- 新计算流程 114/114 项检查通过，见 [运行证据](results/planner-verification.json)。
- 原有叶子函数 38/38 项检查通过，见 [运行证据](results/verification.json)。
- 输入行均检查格式和引用；BOM 结构、循环及库存缺失检查覆盖选中任务的完整可达图。
- 数量仍采用整数草案，日期为日历日，单仓库，无在途、产能、损耗、替代料。
- Python方案仍暂定；规定规模已实测两组固定数据，结果见下方。
- 已支持页面增删改、任务选择、数据版本保存、计划整批保存、历史快照查询与CSV导入导出。完整E3/E4/E5与真实小组评审仍待完成。
- 工作台30/30项浏览器检查通过，见 [交互验证](results/workbench-verification.json)。已检查1440px桌面、390px窄屏、错误定位、断网重试和过期响应丢弃。
- 页面数值输入最大为9007199254740991，超出时明确阻断；计算产生的更大整数以字符串传给页面，保持精确显示。原有Python计算规则不变。
- 本轮保存/API检查36/36、保存与历史浏览器检查14/14、已有界面回归30/30通过。证据分别见 results/storage-verification.json、results/persistence-ui-verification.json、results/workbench-verification.json。测试使用隔离数据库，不污染正式数据。
- CSV解析/API检查38/38、CSV浏览器操作21/21通过，证据见results/csv-verification.json与csv-ui-verification.json。导出文件使用UTF-8 BOM，空风险表仍有表头；所有结果行带计划编号。

## 规定规模性能验证

2026-10-12在本机i7-14650HX上实测两组各200种物料、500条BOM、100项任务的数据，分别覆盖共享库存和最长10条BOM边。每组核心采样5次：中位数0.240/0.222秒，最大值0.241/0.233秒，均低于10秒草案目标；这是固定输入的实测，不保证所有同规模图形均有相同耗时。

另有47/47项核心及保存检查、15/15项浏览器检查通过。浏览器单次“生成计划”到摘要进入视口约1.867/1.737秒，包含实际HTTP、保存、渲染和滚动。测试使用临时数据库，正式数据不受影响。

[性能方法、完整结果与复现步骤](../specs/material-requirements-planning/performance-v0.6.md) · [核心证据](results/performance-verification.json) · [浏览器证据](results/performance-ui-verification.json)

可下载 [共享库存四表数据](results/performance-shared-stock-csv.zip) 或 [10层BOM四表数据](results/performance-deep-zero-stock-csv.zip) 进行演示。两组基准日均为2026-10-01，导入后须点击任务“全选”。大量结果目前完整显示，后续可补分页与筛选。

## 课程详细设计

2026-10-15新增[E3英文Word技术扩展稿](../specs/material-requirements-planning/e3/E3-detailed-design-en.docx)，覆盖14个过程的契约、伪代码、算法图和实际代码映射。小组2人已确认；真实分工与评审、E4/E5完整材料仍待补充。本轮为文档推进，应用版本与计算规则不变。

开源项目取舍见 [GitHub 参考说明](../specs/material-requirements-planning/github-references.md)；设计映射见 [英文阶段说明](../specs/material-requirements-planning/implementation-v0.2.md)。

## E4与E5测试材料更新 2026-10-22

E4白盒和E5黑盒技术报告现已完成；上文E3阶段的待办为历史记录。当前[E5英文Word报告](../specs/material-requirements-planning/e5/E5-black-box-testing-en.docx)共20页，含等价类、边界值、125条通过的HTTP用例及预期/实际结果。浏览器65项、CSV回归38项通过；文档一致性49项通过。套件场景有重叠，不合计为独立需求数量。

E5修复合法CSV长字段触发默认解析上限的问题。超大HTTP请求在Windows上的偶发连接中断仍记录为兼容性问题，未宣称修复。全部测试使用隔离数据库。[E5证据与复现说明](../specs/material-requirements-planning/e5/README.md)。真实两人分工、全员评审和个人贡献仍待补充。
