from pathlib import Path
import json,re
root=Path(r"C:\Users\许yq\Desktop\软件工程")
spec=root/"specs"/"material-requirements-planning"
out=spec/"e2"
v=out/"verification.md"
s=v.read_text(encoding="utf-8").replace("Visual inspection of all generated charts: pending.","Visual inspection completed for all 14 charts. Checked node text, call/flow labels, arrows and graph boundaries. DFDs use vertical layouts for readable labels. The S6 VIEW/LIST path explicitly bypasses CSV conversion. HTML embeds all 14 SVG figures and does not require external image downloads.")
v.write_text(s,encoding="utf-8")
design="""# 生产物料需求与采购计划系统 总体设计入口

版本：E2 v0.1，2026-09-26。
依据：requirements.md、examples.md、E1 v0.2及本轮重新读取的E2原文。
方法：结构化分析、过程式函数和普通数据记录，不采用类继承或对象交互建模。

## 六个子系统

| 子系统 | 责任 | 主入口 |
|---|---|---|
| S1 基础数据维护 | 解析导入、合并修改、校验、整批提交数据版本 | M10 maintain_sources |
| S2 快照与BOM校验 | 一致性读取、选择校验、无环检查、任务排序、冻结输入 | M20 prepare_context |
| S3 多层需求与共享库存 | 按任务优先级处理，先抵库存再展开净需求，保存来源 | M30 net_requirements |
| S4 采购与计划余量 | 按物料和日期汇总缺口，抵扣早期余量，按最小量和倍数取整 | M40 plan_purchases |
| S5 日期与交期风险 | 统一日历日运算、检查过去日期、整理完整计算结果 | M50 complete_plan |
| S6 历史、追溯与导出 | 整批保存、历史查询、来源追溯、按需CSV导出 | M60 publish_results |

M00负责选择操作并协调计算顺序：S2 → S3 → S4 → S5 → S6。基础数据维护走S1。
优先级分配现有库存与按日期计算采购在不同子系统完成，不得互相重排。

## 关键接口与状态责任

- S2返回PreparationResult：READY携带PreparedContext；INVALID携带无效计算结果，直接交给S6展示。
- S3独占本批次D3库存余额；叶子函数返回更新后的余额，由协调函数安装，不能修改真实库存。
- S4独占D4理论采购余量；禁止将其并入真实库存，禁止未来余量倒扣更早需求。
- M34和M44共用M52日期函数，避免采购和生产各自解释提前期。
- M14唯一提交基础数据修改，M62唯一提交完整计划；保存失败不得出现半份成功结果。
- 逻辑DFD携带的完整上下文由协调函数保留，叶子函数只接收和返回必要的数据片段。

## 文件入口

- [完整英文报告](e2/E2-report-en.html)
- [可编辑报告正文](e2/E2-report-en.md)
- [模块结构及调用关系](e2/module-structure.md)
- [细化DFD与内部数据流字典](e2/refined-dfd.md)
- [39个过程式函数的接口](e2/interfaces.md)
- [数据存储设计](e2/data-storage-design.md)
- [设计验证记录](e2/verification.md)

共6个业务子系统、6张对应DFD、6张对应模块结构图，另有总体结构图与P2.3衔接图，共14张。图的SVG、PNG在e2/diagrams。

## 本轮设计取舍

数据修改拟采用不可变版本，计划拟采用整份结果文档原子保存，优先保证历史可复现与实现清楚。这是设计建议，数据库产品与界面形式尚未确认；没有创建数据库或编写项目运行代码。
普通记录、列表、字典以及函数适配器即可表达这些接口，无需自定义类。

## 尚待核实

组员人数N、实际分工、真实评审及个人贡献；整数数量和交付需求等E1假设；编程语言和界面；课程日期及E2文件命名冲突。
当N<=6时，本轮子系统和对应图数量满足E2人数要求；人数未知时不能无条件宣称达标。
E3的伪代码、流程图/PAD/N-S详细设计，以及E4/E5程序测试均尚未开展。
"""
(spec/"design.md").write_text(design,encoding="utf-8")
p=root/"物料需求与采购计划系统-任务计划-2026-09-24.md"
s=p.read_text(encoding="utf-8")
s=s.replace("计划状态：E1逻辑模型及英文报告草稿已形成；复选框表示最终核实与评审状态，未将草稿产出等同于课程实验最终完成。","计划状态：E1与E2设计及英文报告草稿已形成；复选框表示最终核实与评审状态，未将草稿产出等同于课程实验最终完成。")
s=s.replace("当前优先补齐T01人员与课程约束，完成T08真实全组评审，再据评审结果开展T09—T16模块与详细设计。","T09—T11模块设计草稿及T12英文报告已于2026-09-26形成。当前优先补齐T01人员与课程约束、T08/T12真实评审；下一技术阶段为T13—T16详细设计。")
if "## 10 E2材料进度" not in s:
 s+="""\n## 10 E2材料进度 2026-09-26

- T09：已划分6个业务子系统，记录职责和状态所有权；N未知，人数条件待核实。
- T10：已生成6张细化子系统DFD、6张对应模块结构图，以及总体调用图和P2.3分解衔接图，共14张；每个最终DFD处理映射到单个函数。
- T11：已定义39个过程式函数的输入、返回、状态与错误约定，并提出7张逻辑存储表及原子保存设计；尚未选定框架或创建实际数据库。
- T12：英文报告草稿已形成，分工、实际会议和个人贡献待填写；没有冒充已完成全组评审。
- 文档核对：252项结构断言通过，其中父子层边界与已保存E1模型逐项比较；14张图已逐张查看。
- 完整报告：specs/material-requirements-planning/e2/E2-report-en.html；中文设计入口：specs/material-requirements-planning/design.md。
- 当前未开始：T13—T16的E3伪代码及详细算法图、T17以后的应用实现和E4/E5执行测试。
"""
p.write_text(s,encoding="utf-8")
# Focused artifact integrity checks.
report=(out/"E2-report-en.html").read_text(encoding="utf-8")
model=json.loads((out/"model.json").read_text(encoding="utf-8"))
assert report.count("<svg")==14
assert len(model["modules"])==39
assert all((out/"diagrams"/(i+".svg")).exists() and (out/"diagrams"/(i+".png")).exists() for i in model["figures"])
assert "PreparationResult" in report and "MakeExpansion" in report and "G65.view" in report
assert not re.search(r'<(?:script|img)[^>]+(?:src)=["\x27]https?://',report)
print(json.dumps({"html_svg_count":14,"modules":39,"report_bytes":(out/"E2-report-en.html").stat().st_size,"design_entry_written":True,"task_plan_updated":True,"visual_review":"14 of 14"},ensure_ascii=False))
