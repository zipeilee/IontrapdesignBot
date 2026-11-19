"""Build report_input.json for the html-report skill from the measured case data."""

import base64
import json
import pathlib

EX = pathlib.Path(__file__).parent

case_ab = json.load(open(EX / "case_data.json"))
h1, helios = case_ab["h1"], case_ab["helios"]
h2f = json.load(open(EX / "case_h2_final.json"))
h2d = json.load(open(EX / "case_h2_data.json"))
conv = json.load(open(EX / "case_convergence.json"))
h1x = json.load(open(EX / "case_h1_extra.json"))
builtin = json.load(open(EX / "builtin_opt_result.json"))["result"]


def b64(name):
    return base64.b64encode((EX / name).read_bytes()).decode()


def line_rows(series_name, xs, ys, source, note, sample=1, label=""):
    rows = []
    for k in range(0, len(xs), sample):
        rows.append({
            "id": f"{series_name}-{k}",
            "label": label or series_name,
            "x": float(xs[k]),
            "value": float(ys[k]),
            "valueText": repr(float(ys[k])),
            "series": series_name,
            "source": source,
            "notes": [note] if k == 0 else [],
        })
    return rows


# ---------- chart 1: panel convergence ----------
conv_rows = []
for name, rows, src in [
    ("H1 线性阱", h1x["conv"], "case_h1_extra.json/conv"),
    ("H2 跑道", conv["racetrack"], "case_convergence.json/racetrack"),
    ("Helios junction", conv["junction"], "case_convergence.json/junction"),
]:
    for r in rows:
        conv_rows.append({
            "id": f"conv-{name}-{r['panel']}",
            "label": name,
            "x": float(r["panel"]),
            "value": float(r["null_z"]),
            "valueText": repr(float(r["null_z"])),
            "series": name,
            "source": src,
            "notes": [f"面板数 {r['n_panels']}"],
        })

# ---------- chart 2: junction |E|(z) before/after ----------
jx_rows = (
    line_rows("修复前", helios["ez_z"], helios["ez_before"],
              "case_data.json/helios.ez_before", "x_junction, 1 V RF, panel 15 µm",
              sample=2, label="修复前（臂上无中央条）")
    + line_rows("修复后", helios["ez_z"], helios["ez_after"],
                "case_data.json/helios.ez_after", "x_junction + 中央接地条, 1 V RF, panel 15 µm",
                sample=2, label="修复后（臂上有中央条）")
)

# ---------- chart 3: racetrack loop pseudopotential ----------
loop_rows = (
    line_rows("优化前", h2f["s"], h2f["psi_before"],
              "case_h2_final.json/psi_before", "沿实际 null 路径, 200 V @ 42 MHz, panel 6 µm",
              sample=2, label="优化前")
    + line_rows("优化后", h2f["s"], h2f["psi_after"],
                "case_h2_final.json/psi_after", "弯道 7 自由度优化后, panel 6 µm",
                sample=2, label="优化后")
)

# ---------- chart 4: bend optimization milestones ----------
mile_rows = [
    {"id": "m0", "label": "未优化几何", "value": 23.714, "valueText": "23.714",
     "series": "弯道赝势峰", "source": "case_bend_scan.json trim=0",
     "notes": ["对称横截面直接弯成环"]},
    {"id": "m1", "label": "双旋钮网格扫描（28 点）", "value": 6.247, "valueText": "6.247",
     "series": "弯道赝势峰", "parent": "未优化几何",
     "source": "case_bend_refine.json best",
     "notes": ["bend_shift=3 µm, bend_trim=−3.5 µm"]},
    {"id": "m2", "label": "内置优化器 7 自由度（251 次评估）", "value": 1.0155,
     "valueText": "1.0155", "series": "弯道赝势峰", "parent": "双旋钮网格扫描",
     "source": "builtin_opt_result.json obj1_bump_mev",
     "notes": ["optimize_geometry, Nelder-Mead, 11.2 min, panel 8 µm",
               "直道-弯道 null 高度差 0.0065 µm；细面板复验整环峰 24.03→7.72 meV"]},
]

img_h1 = b64("case_h1.png")
img_race = b64("case_racetrack_opt.png")
img_jxb = b64("case_junction_before.png")
img_jxf = b64("case_junction_fixed.png")

LEGEND = ('<p style="font-size:14px;color:var(--muted)">图例：'
          '<span style="color:#ad5036">■</span> 红色 = RF 射频电极（振荡电压，产生囚禁场）；'
          '<span style="color:#4a6f9b">■</span> 蓝色 = DC 控制电极（恒定电压，决定离子位置）；'
          '<span style="color:#5b6c73">■</span> 灰色 = 接地电极（0 V 参照）。'
          '离子悬在电极上方数十微米处，图中不可见。</p>')

report = {
  "title": "IonTrapClaw 能力基准测试：复现 Quantinuum 三代离子阱架构（H1 / H2 / Helios）",
  "lang": "zh-CN",
  "kicker": "技术评估报告 · 离子阱量子计算硬件设计工具",
  "subtitle": "全部数值为 IonTrapClaw 内置 BEM 求解器的真实输出；所有失败与修复均为实测过程记录",
  "sections": [
    {"id": "abstract", "title": "摘要", "html": f"""
<p>IonTrapClaw 是一个把离子阱版图设计接入 AI agent 的 MCP 工具服务：参数化生成表面阱电极、用边界元法（BEM）求解静电场并表征囚禁特性、反解 DC 控制电压、导出制造用 GDS 版图。本报告以 Quantinuum 三代整机架构为基准对象，检验该工具完成真实设计任务的能力边界。</p>
<p>三个案例按拓扑难度递进：<b>H1</b>（线性阱，工具原生支持）、<b>H2</b>（跑道环，测试时工具无此生成器）、<b>Helios</b>（X 形 junction 单元）。主要结果：</p>
<ul>
<li><b>H1 案例</b>：全流程无停顿完成。RF null 高度 25.15 µm，径向囚禁频率 16.3 MHz，中心区 DC 电压反解残差 3.45×10⁻¹¹ V/m。</li>
<li><b>H2 案例</b>：过程中发现两类真实问题——环形电极的"带孔多边形被当实心"几何缺陷（曾产生物理上不可能的赝 null），以及弯道横截面不对称导致的 null 下沉。后者经两轮几何优化，弯道赝势峰从 23.7 meV 压至 1.02 meV（降低 96%），直道与弯道的 null 高度差收敛到 0.0065 µm。</li>
<li><b>Helios 案例</b>：工具评估直接暴露出 junction 生成器缺乏接地中央条的真实设计缺陷（无 RF null，无法囚禁离子）。修复后 null 高度 20.88 µm、阱深 1.44 eV。</li>
<li>三处经验均已固化为工具能力：junction 中央条参数、racetrack 生成器、通用几何优化器 <code>optimize_trap</code>。测试套件 36 项全部通过。</li>
</ul>
<p>能力边界结论：单元级表面阱设计（直线、junction、跑道）已是该工具的可靠工作区；整芯片一次求解受 BEM 稠密矩阵内存限制不可行，须分区评估；多层三维阱与输运动力学不在当前物理模型内。</p>"""},

    {"id": "background", "title": "背景：三代架构与 junction 的角色", "html": """
<p>Quantinuum 的整机均采用 QCCD 架构：芯片被划分为多个工作区（zone），离子在工作区之间物理搬运以完成配对和门操作。三代机器的拓扑演进如下表（数据来源见参考来源）：</p>
<table>
<tr><th></th><th>H1（2021）</th><th>H2（2023）</th><th>Helios（2025）</th></tr>
<tr><td>拓扑</td><td>单条直线走廊</td><td>跑道形闭环</td><td>存储环 + 两条腿（缓存 + 逻辑区）</td></tr>
<tr><td>junction 数量</td><td>0</td><td>0（整环旋转代替交叉）</td><td>1（四路 X junction）</td></tr>
<tr><td>比特数</td><td>20</td><td>32</td><td>98</td></tr>
<tr><td>电极数 / 独立信号数</td><td>198 / 198</td><td>376 / 268</td><td>1228 / 273</td></tr>
<tr><td>离子种类</td><td>¹⁷¹Yb⁺</td><td>¹⁷¹Yb⁺ + ¹³⁸Ba⁺ 冷却</td><td>¹³⁷Ba⁺</td></tr>
</table>
<p>junction 是离子走廊的交叉口，属于基础设施而非量子资源——上面不常驻比特，离子数与 junction 数没有对应关系。它的工程难点在于：产生走廊的射频（RF）电极印在芯片平面上无法立体交叉，交叉口处的电场被扰乱，赝势上拱起"山坡"（RF bump），离子翻越时会被加热。H1 与 H2 刻意绕开 junction（直线排队 + 原地掉头交换；闭环传送带）；Helios 首次在整机中使用一个 X junction 连接存储环与逻辑区，换取存储与计算的解耦并行。</p>
<p>因此三个基准案例恰好分别考察工具的三项能力：线性阱基本功（H1）、非常规拓扑的几何构建与优化（H2）、junction 单元质量评估（Helios）。</p>"""},

    {"id": "method", "title": "方法：工具链与物理模型", "html": """
<p>IonTrapClaw 以 MCP 服务形式运行，agent 通过工具调用完成"生成几何 → 渲染目检 → BEM 评估 → 诊断迭代 → 反解电压 → 导出 GDS"的闭环。本测试涉及的工具：<code>generate_trap</code>（参数化生成器：five_wire / x_junction / t_junction / racetrack）、<code>evaluate_trap</code>（BEM 表征）、<code>solve_dc_voltages</code>（DC 反解）、<code>drc_check</code>（间距检查）、<code>optimize_trap</code>（几何自动寻优，本次测试后新增）。</p>
<p>物理模型：所有电极位于 z = 0 平面，离子在 z &gt; 0 半空间。静电场用第一类边界元法求解：电极剖分为方形面板，点电荷配点法求面电荷密度。RF 约束用赝势近似 Ψ = Q²|E|²/(4mΩ²)（Q 为离子电荷，m 为质量，Ω 为 RF 角频率），囚禁频率由总势的 Hessian 数值求得。该平面假设对 Quantinuum 全系列表面阱成立。</p>
<p>数值纪律：面板边长不得超过最小电极间隙；重要结论须做面板加密收敛性检查。H2 案例表明违反前者会产生"看起来合理"的错误结果。</p>"""},

    {"id": "case-h1", "title": "案例一：H1 型线性阱（原生支持）", "html": f"""
<p>输入规格：¹⁷¹Yb⁺ 线性阱，11 对 DC 分段，RF 100 V @ 30 MHz，评估阱特性并反解中心区电压。生成器 <code>five_wire</code> 直接产出 27 个电极，DRC 一次通过，BEM（4340 面板）表征约 1 秒完成。</p>
{LEGEND}
<figure><img src="data:image/png;base64,{img_h1}" alt="H1 型线性阱版图" style="border:1px solid var(--line)"><figcaption class="figure-caption">图 1：H1 型线性阱版图（five_wire 生成器，11 对 DC 分段）</figcaption></figure>
<table>
<tr><th>指标</th><th>数值</th><th>条件</th></tr>
<tr><td>RF null 高度</td><td>25.15 µm</td><td>panel 10 µm；收敛性见数值方法学</td></tr>
<tr><td>径向囚禁频率</td><td>16.29 / 16.30 MHz</td><td>100 V @ 30 MHz，¹⁷¹Yb⁺</td></tr>
<tr><td>轴向频率</td><td>0.013 MHz</td><td>DC 全接地时轴向自由，属正确物理</td></tr>
<tr><td>DC 反解残差</td><td>3.45×10⁻¹¹ V/m</td><td>目标点 (0, 0, 25.1 µm) 场归零</td></tr>
<tr><td>DC 电压范围</td><td>−0.148 ~ +1.000 V</td><td>DAC 友好区间</td></tr>
</table>
<p>该案例全程无停顿：直线阱是工具的成熟工作区，可作基准测试的基本功基线。</p>"""},

    {"id": "case-h2", "title": "案例二：H2 型跑道环（几何构建 + 弯道优化）", "html": f"""
<p>输入规格：跑道形闭环（无 junction），¹⁷¹Yb⁺，RF 取 H2 真实工作点 200 V @ 42 MHz。测试时工具无跑道生成器，通过通用脚本接口构建：同心双 RF 环 + 接地中环 + 直道 DC 分段 + 端帽地（22 电极）。该构建器随后固化为 <code>racetrack</code> 生成器。</p>
{LEGEND}
<figure><img src="data:image/png;base64,{img_race}" alt="H2 型跑道环版图（弯道已优化）" style="border:1px solid var(--line)"><figcaption class="figure-caption">图 2：H2 型跑道环版图（图示为弯道优化后的几何）</figcaption></figure>
<h3>过程记录 1：数值假象的发现</h3>
<p>第一版几何在粗面板（12 µm）下给出完全合理的表象：null 高度 20.65 µm、径向频率 21.4 MHz。但加密面板（6 µm）后 null 消失，且施加 1 V 的电极在空间点算出 −8.5 V 的电势——违反静电场最大值原理，必为几何或离散错误。根因：环形电极是"带孔多边形"，数据模型只保存外轮廓，环被当成实心盘，与中心接地电极重叠，边界条件自相矛盾。修复方式：把环切分为上下两个无孔半环。教训：<b>对"好得可疑"的结果必须做收敛性检查</b>。</p>
<h3>过程记录 2：弯道几何优化</h3>
<p>修复后发现真实物理问题：弯道上内外侧电极弧长不等，横截面不对称，弯道 RF null 比直道低 1.74 µm，赝势沿环出现 23.7 meV 的峰（离子运输经过时会被加热）。优化分两轮：先以两个手工参数（弯道整体半径偏移、内外 RF 环宽度补偿）网格扫描 28 个设计点，峰压至 6.25 meV 但 null 下沉残留 0.93 µm；再放开弯道全部 7 条电极边界做 Nelder-Mead 自由寻优（间隙 ≥ 3.5 µm 硬约束）。该流程随后固化为内置工具 <code>optimize_trap</code>，用内置工具复跑的结果如下：</p>
<div data-chart="bend_milestones"></div>
<div data-chart="loop_psi"></div>
<p>整环残余的 7.72 meV 峰位于直道与弯道的接缝处——那里剖面是突变的；继续压平需要剖面沿弧长渐变（taper），属于下一级自由度，不再影响走廊本身的均匀性。</p>"""},

    {"id": "case-helios", "title": "案例三：Helios 型 X junction（缺陷发现与修复）", "html": f"""
<p>输入规格：四路 X junction 单元（Helios 核心结构），¹³⁷Ba⁺，RF 120 V @ 25 MHz，评估走廊阱特性。生成器产出 41 个电极后，<code>evaluate_trap</code> 直接报错：找不到囚禁点。沿臂中线扫描场强发现其随高度单调衰减——<b>该几何根本没有 RF null</b>。根因：junction 四条臂的两根 RF 轨道之间缺少接地中央条（线性阱生成器中有此电极，junction 生成器中遗漏），同电位双轨道等效为单根宽导体，无法形成四极场。</p>
<table style="width:auto"><tr>
<td style="border:none;padding-right:12px"><img src="data:image/png;base64,{img_jxb}" alt="修复前 junction 版图" style="border:1px solid var(--line)"></td>
<td style="border:none"><img src="data:image/png;base64,{img_jxf}" alt="修复后 junction 版图" style="border:1px solid var(--line)"></td>
</tr><tr><td style="border:none" class="figure-caption">图 3a：修复前（臂上 RF 轨道间为空衬底）</td><td style="border:none" class="figure-caption">图 3b：修复后（每臂补一条接地中央条，灰色）</td></tr></table>
<div data-chart="jx_field"></div>
<p>修复后表征：null 高度 20.88 µm、阱深 1.44 eV（走廊尽头 RF 终止形成的真实势垒）、径向频率 41.0 MHz。修复已固化为生成器参数 <code>center_strip=True</code>（默认开启），并配有"无中央条则无 null"的物理回归测试。该案例展示了"生成 → 物理验证 → 缺陷诊断 → 修复固化"闭环的价值：此类缺陷目检版图极难发现，只有场求解能暴露。</p>"""},

    {"id": "numerics", "title": "数值方法学：收敛性与规模上限", "html": """
<p>三个案例的 RF null 高度对面板密度的依赖如下。粗面板（12 µm）与最细面板（4 µm）之间变化均小于 2%，说明几何正确时 null 位置对面板密度不敏感；但 H2 案例同时证明，几何有缺陷时粗面板会给出稳定的错误答案——收敛性检查是必要纪律而非可选步骤。</p>
<div data-chart="conv"></div>
<h3>BEM 规模上限（稠密矩阵）</h3>
<table>
<tr><th>面板数</th><th>交互矩阵内存</th><th>实测求解时间</th></tr>
<tr><td>约 4,000</td><td>128 MB</td><td>&lt; 1 s</td></tr>
<tr><td>约 10,000</td><td>0.9 GB</td><td>约 6 s（全新进程）</td></tr>
<tr><td>约 16,000</td><td>2.1 GB</td><td>约 25 s</td></tr>
<tr><td>约 27,000</td><td>6 GB</td><td>分钟级以上；长时间会话中观察到数量级恶化（内存累积），建议大型求解在独立进程中运行</td></tr>
<tr><td>2 mm² 整芯片 @ 10 µm 面板</td><td>约 13 GB</td><td>不可行——必须按单元分区评估</td></tr>
</table>
<p>结论：整芯片一次性静电求解超出当前实现的能力，正确策略（也是业界惯例）是单元级精算 + 系统级只做几何与规则检查。</p>"""},

    {"id": "discussion", "title": "讨论：能力边界与基准设计", "html": """
<h3>能力边界画像</h3>
<table>
<tr><th>层级</th><th>状态</th></tr>
<tr><td>直线阱 / junction / 跑道单元级设计与验证</td><td>原生支持，闭环分钟级</td></tr>
<tr><td>几何自动寻优（null 高度、区域一致性、路径赝势峰 + 间隙约束）</td><td>已内置（optimize_trap），本报告弯道优化即由其完成</td></tr>
<tr><td>多 junction 网格拼装、整芯片静电求解</td><td>超出当前能力（需分区策略 + 求解器加速）</td></tr>
<tr><td>多层三维阱、微运动动力学、加热率模型</td><td>不在当前物理模型内</td></tr>
</table>
<h3>作为基准测试的建议评分维度</h3>
<ul>
<li><b>效率</b>：达成规格的迭代轮数与工具调用数；面板密度选择的合理性。</li>
<li><b>物理判断力</b>：是否主动做收敛性检查；能否识别"好得可疑"的假 null；对轴向/环向自由度导致的低阱深能否正确解读。</li>
<li><b>工程产出</b>：GDS/JSON 可复开复算；DC 电压幅值可行性；发现的缺陷是否固化为生成器修复与回归测试。</li>
</ul>
<h3>本次测试已固化的改进</h3>
<ul>
<li>junction 生成器新增接地中央条（默认开启）+ 物理回归测试；</li>
<li><code>racetrack</code> 跑道生成器入库，弯道剖面全参数化；</li>
<li>通用几何优化器 <code>optimize_trap</code>（目标与约束 JSON 化，Nelder-Mead 闭环，最优几何直接载入版图）；</li>
<li>测试套件从 29 项扩至 36 项，全部通过。</li>
</ul>"""},

    {"id": "glossary", "title": "术语表（点击展开）", "html": """
<details><summary><b>RF（射频电压）</b></summary><p>每秒振荡几千万次的电压（如 30 MHz）。离子跟不上振荡，只感受平均效果——等效为一根把离子按在半空的"无形弹簧"。RF 电压越高、频率越快，束缚越紧。不能改用直流：静电学定理（Earnshaw）禁止纯电场在三维同时囚禁带电粒子。</p></details>
<details><summary><b>RF null（射频零场线）</b></summary><p>电极排布合适时，芯片上方某条线上振荡电场恰好抵消为零，离子待在线上几乎不受力。"离子高度"即此线离芯片的距离（典型几十微米）。"|E|(z) 图上的深谷"就是它；找不到谷 = 困不住离子。</p></details>
<details><summary><b>赝势（pseudopotential）</b></summary><p>快速振荡电场的平均效果等效成静止势能面：Ψ = Q²|E|²/(4mΩ²)。场强越大的地方势能越高，离子因此被推向场最弱的 RF null。阱深、囚禁频率都由它算出。</p></details>
<details><summary><b>囚禁频率（secular frequency）</b></summary><p>离子在赝势碗中振动的快慢（MHz）。沿走廊方向称轴向，垂直方向称径向。径向典型几 MHz，轴向不到 1 MHz。量子门的速度上限由它决定。</p></details>
<details><summary><b>阱深（trap depth）</b></summary><p>离子逃逸需翻越的最低势垒（eV）。参考：室温热动能约 0.025 eV，阱深至少要比它大几十倍。本报告 H1/H2 案例的低阱深（10⁻⁶~10⁻⁵ eV）是因为尚未施加 DC 轴向束缚，属正确物理而非错误。</p></details>
<details><summary><b>BEM（边界元法）与面板</b></summary><p>把电极表面切成小方块（面板），求解每块上的电荷使电极电压等于设定值，再叠加出空间任意点的场。面板越细越准，但内存随面板数平方、时间近立方增长。经验法则：面板边长 ≤ 最小电极间隙。</p></details>
<details><summary><b>收敛性检查</b></summary><p>同一几何用粗、细两档面板各算一遍，结果几乎不变才可信。H2 案例中粗面板曾给出稳定但错误的结果（假 null），收敛性检查是揭发它的唯一手段。</p></details>
<details><summary><b>DC 电极与 DC 反解</b></summary><p>DC = 恒定电压电极，负责"在绳索上划停车位"：决定离子停在走廊何处、何时搬家。反解是反过来：指定"离子在目标点不受力"，用最小二乘反推各电极电压。搬运离子 = 目标点移动一小步、反解一次、连成电压序列。</p></details>
<details><summary><b>junction（交叉口）</b></summary><p>两条离子走廊的交叉结构，让离子拐弯换道。平面芯片上 RF 电极无法立体交叉，交叉口场被扰乱形成赝势山坡（RF bump），离子翻越时被加热。junction 几何优化（压低山坡）是 QCCD 路线的核心工程问题。</p></details>
<details><summary><b>QCCD 与 zone</b></summary><p>量子电荷耦合器件架构：芯片划分多个工作区（zone）——做门操作的"车间"、存储的"仓库"等，离子在区间物理搬运。换来的是每次只操作少量离子的高保真度，代价是搬运耗时与加热，因此 zone 布局是关键设计问题。</p></details>
<details><summary><b>表面阱（surface trap）</b></summary><p>把所有电极印在一片平整芯片表面（而非三维金属杆），电场从平面拱起囚禁离子。可用半导体光刻制造任意图案——这正是本工具的设计对象，也是"所有电极共面"假设成立的原因。</p></details>
<details><summary><b>微运动（micromotion）</b></summary><p>离子偏离 RF null 时被振荡电场推着快速小抖动，干扰激光操作。需用 DC 电压补偿归零；junction 山坡是过路离子微运动的主要来源。</p></details>
<details><summary><b>协同冷却（sympathetic cooling）</b></summary><p>计算离子不能随意用激光照（会破坏量子态），于是混入另一种"冷却剂"离子（如 Ba⁺），激光只冷却它，靠库仑碰撞带走计算离子的热量。H2 用 ¹⁷¹Yb⁺ 计算 + ¹³⁸Ba⁺ 冷却。</p></details>
<details><summary><b>GDS 与 DRC</b></summary><p>GDS 是芯片制造的标准版图文件格式（施工图纸）；DRC 是晶圆厂的设计规则检查（如最小线间距）。本工具输出 GDS 并做基础间距检查；真实流片需过晶圆厂完整规则包。</p></details>
<details><summary><b>optimize_trap（几何自动寻优）</b></summary><p>本报告测试后新增的内置工具：以 JSON 描述优化目标（null 高度命中 / 多区域 null 一致 / 路径赝势峰）与硬约束（最小电极间隙），Nelder-Mead 自动迭代几何参数，每次迭代都是一次完整的 BEM 求解，最优几何直接载入版图。</p></details>"""},

    {"id": "references", "title": "参考来源", "html": """
<ul>
<li>Pino, J. M. <i>et al.</i> "Demonstration of the trapped-ion quantum CCD computer architecture"（H1）, Nature 592, 209 (2021). <a href="https://arxiv.org/abs/2003.01293">arXiv:2003.01293</a></li>
<li>Moses, S. A. <i>et al.</i> "A race-track trapped-ion quantum processor"（H2）, Phys. Rev. X 13, 041052 (2023). <a href="https://arxiv.org/abs/2305.03828">arXiv:2305.03828</a></li>
<li>Ransford, A. <i>et al.</i> "Helios: A 98-qubit trapped-ion quantum computer"（Helios）. <a href="https://arxiv.org/abs/2511.05465">arXiv:2511.05465</a>；<a href="https://www.nature.com/articles/s41586-026-10676-4">Nature 正式版 (2026)</a></li>
<li>Delaney, R. D. <i>et al.</i> "Scalable multispecies ion transport in a grid-based surface-electrode trap", Phys. Rev. X 14, 041028 (2024). <a href="https://journals.aps.org/prx/abstract/10.1103/PhysRevX.14.041028">期刊页</a></li>
<li>Bruzewicz, C. D. <i>et al.</i> "Trapped-ion quantum computing: progress and challenges"（综述）. <a href="https://arxiv.org/abs/1904.04178">arXiv:1904.04178</a></li>
<li>Wesenberg, J. H. "Electrostatics of surface-electrode ion traps", Phys. Rev. A 78, 063410 (2008). <a href="https://arxiv.org/abs/0808.1623">arXiv:0808.1623</a></li>
<li>本报告全部数值产物：仓库 <code>examples/</code> 目录下的 case_*.json / bend_*.json 记录与对应 PNG 版图。</li>
</ul>"""},
  ],
  "charts": [
    {"id": "conv", "title": "图 4：RF null 高度的面板收敛性", "type": "line",
     "xLabel": "面板边长 / µm", "yLabel": "null 高度", "valueLabel": "null 高度",
     "unit": "µm", "connect": True,
     "caption": "同一几何在不同面板密度下的 null 高度。三条曲线各自的点不可互相比较条件（几何不同）；同一系列内连线仅表示加密趋势。",
     "rows": conv_rows},
    {"id": "jx_field", "title": "图 5：junction 臂中线上方 RF 场强 |E|(z)，修复前后", "type": "line",
     "xLabel": "高度 z / µm", "yLabel": "|E|", "valueLabel": "|E|（1 V RF）",
     "unit": "V/m", "connect": True,
     "caption": "修复后曲线在 z ≈ 20 µm 处的深谷即 RF null（囚禁点）；修复前无谷，几何无法囚禁离子。隔点采样（原 60 点/系列取 30 点）。",
     "rows": jx_rows},
    {"id": "loop_psi", "title": "图 6：赝势沿跑道环一周，弯道优化前后", "type": "line",
     "xLabel": "沿环弧长 / µm", "yLabel": "赝势", "valueLabel": "赝势",
     "unit": "meV", "connect": True,
     "caption": "沿各段实际 null 位置、直道 null 高度扫描。两个峰对应两个 180° 弯道；优化后残余峰位于直道-弯道接缝。隔点采样（原 240 点/系列取 120 点）。",
     "rows": loop_rows},
    {"id": "bend_milestones", "title": "图 7：弯道赝势峰的优化进程", "type": "dot",
     "xLabel": "弯道赝势峰 / meV", "valueLabel": "弯道赝势峰", "unit": "meV",
     "caption": "同一弯道弧扫描度量（panel 8 µm）下的三个阶段结果；差值为配对比较（同一几何族逐步优化）。",
     "rows": mile_rows},
  ],
  "footer": "本报告由 IonTrapClaw 仓库实测数据构建；图表数据为隔点采样，完整数值见各图附表与 examples/ 原始记录。",
}

out = EX / "report_input.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", out, out.stat().st_size)
