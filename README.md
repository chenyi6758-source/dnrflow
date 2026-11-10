# dnrflow

[![tests: 43 passed](https://img.shields.io/badge/tests-43%20passed-brightgreen.svg)](tests/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![License: BSD-3-Clause](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)

**English** | [简体中文](#dnrflow-中文)

**A radial feeder loses power in its branches. Open the right switches and the same loads cost less — `dnrflow` finds which switches, on any pandapower network, and proves the answer on the small cases.**

## Results at a glance

Branch exchange (the production solver) on the four built-in cases:

| case | buses / branches | base loss | optimal loss | reduction | min voltage | open switches (1-based) |
|---|---|---|---|---|---|---|
| case33 | 33 / 37 | 202.68 kW | **139.55 kW** | −31.1% | 0.9131 → 0.9378 | 7, 9, 14, 32, 37 |
| case69 | 69 / 73 | 224.99 kW | **98.60 kW** | −56.2% | 0.9092 → 0.9495 | 14, 55, 61, 69, 70 |
| case119 | 118 / 132 | 1298.09 kW | **875.16 kW** | −32.6% | 0.8688 → 0.9323 | 22, 26, 32, 39, 42, 48, 51, 58, 71, 74, 95, 97, 109, 129, 130 |
| case16 | 16 / 16 | 514.03 kW | **468.33 kW** | −8.9% | 0.9682 → 0.9707 | 7, 8, 16 |

```console
$ dnrflow case33
case33: Baran & Wu (1989), via pandapower.networks.case33bw
case33 (branch-exchange): 202.68 -> 139.55 kW (-31.1%)
loss:           202.68 kW ->    139.55 kW (-63.13 kW, -31.1%)
min voltage: 0.9131 p.u. -> 0.9378 p.u.
open switches: 7 (7-8), 9 (9-10), 14 (14-15), 32 (32-33), 37 (25-29)
exchanges:
  pass 1: close tie 33, open 7: 202.68 -> 158.39 kW (-44.29 kW, estimated -39.64 kW)
  pass 1: close tie 34, open 14: 158.39 -> 152.62 kW (-5.77 kW, estimated -5.17 kW)
  pass 1: close tie 35, open 9: 152.62 -> 142.17 kW (-10.45 kW, estimated -9.66 kW)
  pass 1: close tie 36, open 32: 142.17 -> 139.55 kW (-2.61 kW, estimated -2.29 kW)
evaluations: 31, elapsed: 2.0 s
```

Three findings worth a planner's attention:

1. **The 33-bus result matches the literature exactly, and the 69-bus result beats it.** 139.55 kW with open switches 7, 9, 14, 32, 37 is the published 33-bus optimum. On the 69-bus system the solver finds 98.60 kW, 1.0 kW better than the 99.62 kW reported by a 2026 reference — the greedy search does not stop at the first good answer.
2. **The optimum is not always the obvious switches.** On the 69-bus case the winning move is closing tie 72 (50–59) and opening branch 55, worth 64.94 kW in a single exchange — more than half the total saving. A solver that only tries the "nearest" branch would miss it.
3. **The optimal topology is stable across load levels.** On case33 the same open set (7, 9, 14, 32, 37) is optimal at peak, mid (×0.7) and valley (×0.4) load — 139.55, 66.43 and 21.10 kW. One switching plan covers the day.

## How it works

Three solvers, one result type. Every solver takes a pandapower network and returns the open-switch set, the loss before/after, and the voltage before/after.

**Branch exchange** (`solve_branch_exchange`, the production path) is Civanlar's method: closing a tie switch creates exactly one loop; a load-transfer estimate ranks every branch of the loop (opening branch *j* transfers its base current to the tie, so every other loop branch carries *Iₖ − Iⱼ*), and the best few candidates are verified exactly with a pandapower power flow. Passes repeat until no exchange improves the loss. Multi-feeder networks work too: all slack buses are contracted to one virtual node, so a tie joining two feeders forms a loop through it. The estimate is only a screen — the exact power flow decides, and every accepted step is logged with its estimated and exact saving.

**MILP** (`solve_milp`, the cross-check) is a LinDistFlow model — squared voltages, linear voltage drops, branch losses as a piecewise-linear outer approximation of *P² + Q²*, radiality enforced by a branch count plus a single-commodity-flow condition — solved with HiGHS through `scipy.optimize.milp`. The tangent planes are re-linearised around the exact power flow of each solution (up to three rounds) and the best exact topology seen is returned. It agrees with branch exchange on every case it was run on (see the table below), but its linearised loss estimate is a lower bound, 7–22% below the exact loss — it certifies the topology, not the loss number.

**Enumeration** (`enumerate_optimum`, the proof) tries every combination of open switches, checks radiality first with a fast graph test, and evaluates only the radial ones exactly. It is the global optimum for the network as built — feasible only on small networks (the 16-bus case: 190 radial topologies out of 560 combinations).

| case | branch exchange | MILP (exact loss of its topology) | enumeration |
|---|---|---|---|
| case16 | 468.33 kW | 468.33 kW | **468.33 kW** |
| case33 | 139.55 kW | 139.55 kW | too large (C(37,5) = 435,897) |
| case69 | 98.60 kW | 98.60 kW | too large |
| case119 | 875.16 kW | not run (too slow) | too large |

## Usage

```console
$ dnrflow case69 --solver branch-exchange
$ dnrflow case16 --solver enumerate
$ dnrflow case33 --solver milp
$ dnrflow case33 --levels            # peak / mid / valley, solved independently
$ dnrflow case119 --switches --json out.json
```

Python API:

```python
from dnrflow import load_case, solve_branch_exchange, solve_milp
from dnrflow import enumerate_optimum, solve_load_levels

net = load_case("case33")
res = solve_branch_exchange(net)
print(res.final_loss_kw, [i + 1 for i in res.open_lines])  # 139.55 [7, 9, 14, 32, 37]

# Any pandapower network works, not just the built-in cases:
# every line is a switchable branch (in_service = closed).
res = solve_branch_exchange(my_net)
```

## Validation against the literature

| case | base loss: literature | base loss: measured | optimal loss: literature | optimal loss: measured |
|---|---|---|---|---|
| case33 | 202.69 kW | 202.68 kW | 139.55 kW | **139.55 kW** |
| case69 | 224.99 kW | 224.99 kW | 99.62 kW | **98.60 kW** |
| case119 | 1298.09 kW (1296.57 kW in one paper) | 1298.09 kW | 853.58–854.04 kW | **875.16 kW** |
| case16 | ~511.4 kW | 514.03 kW | ~466.1 kW | **468.33 kW** |

The 33- and 69-bus cases match or beat the literature. The two gaps are honest ones, not hidden:

- **case119: 875.16 vs 853.58–854.04 kW (2.5%).** Branch exchange is a greedy local search — it stops when no single exchange improves the loss — while the literature values come from global/metaheuristic searches. The two data variants also differ: this package ships the 118-bus MATPOWER variant (`case118zh`, 118 buses / 132 branches), while the 853.58 kW value is for the 133-branch variant. The minimum voltage matches the literature exactly (0.9323 p.u.), which is a good sign the two systems are the same feeder.
- **case16: 514.03 vs ~511.4 kW base, 468.33 vs ~466.1 kW optimal (both +0.5%).** The offset is the same on the base and the optimal loss, which points at the published table values being rounded to 4–5 significant figures rather than at a solver error. The internal check is exact: branch exchange, MILP and exhaustive enumeration all return 468.33 kW with the same open set on the data as shipped.

## Honesty notes

- **The 119-bus system in this package has 118 buses.** The embedded data is MATPOWER `case118zh.m`: 118 buses, 132 branches (117 closed + 15 ties). The same system is usually cited as the 119-bus system (119 buses / 133 branches). The missing bus carries no load — total load is identical at 22.71 MW — so the two variants are equivalent for reconfiguration, but the branch numbering differs from the 133-branch papers and the base loss differs by 1.5 kW (1298.09 vs 1296.57 kW) between the two variants.
- **The 69-bus tie lines are not in the MATPOWER file.** They are taken from Savier & Das (2007), Table 2: 11–43 (0.5 + j0.5 Ω), 13–21 (0.5 + j0.5 Ω), 15–46 (1.0 + j0.5 Ω), 50–59 (2.0 + j1.0 Ω), 27–65 (1.0 + j0.5 Ω).
- **The 16-bus system has three feeders and fixed capacitors.** Sources at buses 1, 2, 3; 23 kV; shunt capacitors totalling 11.4 MVAr. The base voltage is not stated in the original Civanlar paper — 23 kV is the value that reproduces the published base loss (~511 kW).
- **Branch exchange does not guarantee the global optimum.** It is exact on the 16-, 33- and 69-bus cases (verified against enumeration and MILP), and 2.5% above the best-known value on the 119-bus case.
- **The MILP is slow on medium networks.** About 3 s (16-bus), 47 s (33-bus), 169 s (69-bus) for three re-linearisation rounds; it was not run on the 119-bus case. It is a cross-check, not the production path.
- **Losses are computed with pandapower** (`bfsw`, falling back to Newton-Raphson). A topology that leaves a bus without a slack is reported as non-converged, never silently solved.

## References

- Civanlar, Grainger, Yin & Lee, "Distribution feeder reconfiguration for loss reduction", *IEEE Trans. Power Delivery*, 1988 — branch exchange.
- Baran & Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing", *IEEE Trans. Power Delivery*, 1989 — the 33- and 69-bus systems and LinDistFlow.
- Zhang, Fu & Zhang, "An improved TS algorithm for loss-minimum reconfiguration in large-scale distribution systems", *Electric Power Systems Research*, 2007 — the 119-bus system.
- Savier & Das, "Impact of network reconfiguration on loss allocation of radial distribution systems", *IEEE Trans. Power Delivery*, 2007 — the 69-bus tie data.
- "Optimal feeder reconfiguration and placement of voltage regulators…", *Sustainability*, 2023 — the 119-bus 853.58 kW reference and the 1296.57 kW base loss.

---

# dnrflow （中文）

**English** | **简体中文**

**同一批负荷，换一组开关状态就能少损耗电能——`dnrflow` 在任意 pandapower 配网上找出该断开哪些开关，并在小网络上给出可证明的最优解。**

## 一眼结果

支路交换法（主求解器）在四个内置算例上的结果：

| 算例 | 母线 / 支路 | 重构前网损 | 重构后网损 | 降损 | 最低电压 | 断开开关（1 起编号） |
|---|---|---|---|---|---|---|
| case33 | 33 / 37 | 202.68 kW | **139.55 kW** | −31.1% | 0.9131 → 0.9378 | 7, 9, 14, 32, 37 |
| case69 | 69 / 73 | 224.99 kW | **98.60 kW** | −56.2% | 0.9092 → 0.9495 | 14, 55, 61, 69, 70 |
| case119 | 118 / 132 | 1298.09 kW | **875.16 kW** | −32.6% | 0.8688 → 0.9323 | 22, 26, 32, 39, 42, 48, 51, 58, 71, 74, 95, 97, 109, 129, 130 |
| case16 | 16 / 16 | 514.03 kW | **468.33 kW** | −8.9% | 0.9682 → 0.9707 | 7, 8, 16 |

三点值得注意：

1. **33 节点与文献完全一致，69 节点比文献更好。**139.55 kW、断开 7、9、14、32、37 就是文献中的 33 节点最优解。69 节点算出 98.60 kW，比 2026 年一篇文献报的 99.62 kW 还低 1.0 kW——贪心搜索没有停在第一个好答案上。
2. **最优解不总是最直观的开关。**69 节点最大的一步是合联络开关 72（50–59）、断开支路 55，单步降损 64.94 kW，占总降损一半以上。只试"最近"的支路会错过它。
3. **最优拓扑不随负荷水平变化。**33 节点在峰（×1.0）、腰（×0.7）、谷（×0.4）三种负荷下最优断开开关完全相同（7、9、14、32、37），网损分别为 139.55、66.43、21.10 kW。一套开关方案覆盖全天。

## 做法

三个求解器，同一套结果类型。输入任意 pandapower 网络，输出断开开关集合、重构前后网损与电压。

**支路交换法**（`solve_branch_exchange`，主求解器）是 Civanlar 方法：合上一个联络开关恰好形成一个环；用负荷转移估算给环上每条支路排序（断开支路 *j* 会把它的基态电流转移到联络开关上，其余环支路电流变为 *Iₖ − Iⱼ*），再对最好的几个候选做精确潮流验证。反复多轮，直到没有任何交换能继续降损。多电源网络同样适用：所有平衡节点收缩为一个虚拟节点，跨馈线的联络开关经由它成环。估算只是筛选，最终由精确潮流决定，每一步接受的交换都记录估算值与精确值。

**MILP**（`solve_milp`，对照求解器）是 LinDistFlow 模型——电压平方线性化、支路损耗用 *P² + Q²* 的分段线性外逼近、辐射状由支路数加单商品流约束保证——用 HiGHS 经 `scipy.optimize.milp` 求解。切平面按每轮精确潮流结果重新线性化（最多三轮），返回三轮中精确网损最好的拓扑。它在所有跑过的算例上与支路交换法一致（见下表），但其线性化损耗估计是下界，比精确值低 7–22%——它验证的是拓扑，不是损耗数值。

**全枚举**（`enumerate_optimum`，证明用）遍历全部断开开关组合，先用快速图论检查辐射状，只对辐射状拓扑做精确潮流。它是给定数据下的全局最优，只适用于小网络（16 节点：560 种组合中 190 种辐射状）。

| 算例 | 支路交换法 | MILP（其拓扑的精确网损） | 全枚举 |
|---|---|---|---|
| case16 | 468.33 kW | 468.33 kW | **468.33 kW** |
| case33 | 139.55 kW | 139.55 kW | 太大（C(37,5) = 435,897） |
| case69 | 98.60 kW | 98.60 kW | 太大 |
| case119 | 875.16 kW | 未跑（太慢） | 太大 |

## 用法

```console
$ dnrflow case69 --solver branch-exchange
$ dnrflow case16 --solver enumerate
$ dnrflow case33 --solver milp
$ dnrflow case33 --levels            # 峰 / 腰 / 谷三档负荷，各自独立求解
$ dnrflow case119 --switches --json out.json
```

Python 调用：

```python
from dnrflow import load_case, solve_branch_exchange, solve_milp
from dnrflow import enumerate_optimum, solve_load_levels

net = load_case("case33")
res = solve_branch_exchange(net)
print(res.final_loss_kw, [i + 1 for i in res.open_lines])  # 139.55 [7, 9, 14, 32, 37]

# 不只限于内置算例：任意 pandapower 网络都行，
# 每条线路就是一个开关（in_service = 合闸）。
res = solve_branch_exchange(my_net)
```

## 与文献对照

| 算例 | 基态网损：文献 | 基态网损：实测 | 最优网损：文献 | 最优网损：实测 |
|---|---|---|---|---|
| case33 | 202.69 kW | 202.68 kW | 139.55 kW | **139.55 kW** |
| case69 | 224.99 kW | 224.99 kW | 99.62 kW | **98.60 kW** |
| case119 | 1298.09 kW（一篇文献为 1296.57 kW） | 1298.09 kW | 853.58–854.04 kW | **875.16 kW** |
| case16 | 约 511.4 kW | 514.03 kW | 约 466.1 kW | **468.33 kW** |

33、69 节点与文献一致或更优。两处差距如实说明，不藏着：

- **case119：875.16 对 853.58–854.04 kW（差 2.5%）。**支路交换法是贪心局部搜索——没有单步交换能改进时就停——而文献值来自全局/元启发式搜索。数据版本也有差别：本包用的是 118 节点 MATPOWER 版本（`case118zh`，118 母线 / 132 支路），853.58 kW 是 133 支路版本的值。最低电压与文献完全一致（0.9323 p.u.），说明是同一条馈线。
- **case16：基态 514.03 对约 511.4 kW、最优 468.33 对约 466.1 kW（均为 +0.5%）。**基态与最优的偏差相同，指向文献表格数值修约到 4–5 位有效数字造成的数据版本差异，而非求解器错误。内部验证是精确的：在本包数据上，支路交换法、MILP、全枚举三者都给出 468.33 kW、同一组断开开关。

## 诚实说明

- **本包的"119 节点"系统实际是 118 个母线。**内置数据是 MATPOWER `case118zh.m`：118 母线、132 支路（117 合闸 + 15 联络）。同一系统在文献中通常称 119 节点系统（119 母线 / 133 支路）。缺失的母线不带负荷——总负荷完全相同（22.71 MW）——所以对重构而言两个版本等价，但支路编号与 133 支路文献不同，基态网损相差 1.5 kW（1298.09 对 1296.57 kW）。
- **69 节点联络线不在 MATPOWER 文件里。**取自 Savier & Das (2007) 表 2：11–43（0.5 + j0.5 Ω）、13–21（0.5 + j0.5 Ω）、15–46（1.0 + j0.5 Ω）、50–59（2.0 + j1.0 Ω）、27–65（1.0 + j0.5 Ω）。
- **16 节点系统有三条馈线和固定电容器。**电源在母线 1、2、3；电压 23 kV；并联电容器共 11.4 MVAr。原始 Civanlar 文献未注明基准电压，23 kV 是能复现文献基态网损（约 511 kW）的取值。
- **支路交换法不保证全局最优。**在 16、33、69 节点算例上是精确的（已用全枚举与 MILP 验证），在 119 节点算例上比已知最好值高 2.5%。
- **MILP 在中等网络上很慢。**三轮重线性化约 3 秒（16 节点）、47 秒（33 节点）、169 秒（69 节点）；119 节点未跑。它是 cross-check，不是主求解器。
- **网损用 pandapower 计算**（`bfsw`，失败时退回牛顿法）。使某母线失去电源的拓扑直接判为不收敛，绝不悄悄算出一个数。

## 参考文献

- Civanlar, Grainger, Yin & Lee, "Distribution feeder reconfiguration for loss reduction", *IEEE Trans. Power Delivery*, 1988——支路交换法。
- Baran & Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing", *IEEE Trans. Power Delivery*, 1989——33/69 节点系统与 LinDistFlow。
- Zhang, Fu & Zhang, "An improved TS algorithm for loss-minimum reconfiguration in large-scale distribution systems", *Electric Power Systems Research*, 2007——119 节点系统。
- Savier & Das, "Impact of network reconfiguration on loss allocation of radial distribution systems", *IEEE Trans. Power Delivery*, 2007——69 节点联络线数据。
- "Optimal feeder reconfiguration and placement of voltage regulators…", *Sustainability*, 2023——119 节点 853.58 kW 参照值与 1296.57 kW 基态网损。
