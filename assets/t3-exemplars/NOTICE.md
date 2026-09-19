# 参考图库 —— 版权说明

## 本仓库包含的图（可自由再分发）

| 文件 | 来源 | 许可 |
|---|---|---|
| `T3-02_STAR2024_ED1_*.png` | STAR Collaboration, *Imaging shapes of atomic nuclei in high-energy nuclear collisions*, **Nature 635** (2024), DOI [10.1038/s41586-024-08097-2](https://doi.org/10.1038/s41586-024-08097-2) | **CC-BY 4.0**（开放获取） |
| `T3-03_STAR2024_phi角示意_*.png` | 同上，Extended Data Fig. 1 panel g | **CC-BY 4.0** |

引用时请注明原论文。图本身版权归原作者，依 CC-BY 许可再分发。

## 本仓库**不包含**的图（版权受限）

以下参考图**因版权原因未随仓库分发**。你需要从有访问权的渠道自行获取
（机构订阅 / 开放获取版本 / arXiv），再用 `scripts/extract_figures.py` 切图：

| 代号 | 来源 | 状态 | 获取方式 |
|---|---|---|---|
| T3-01 | Jia, Zhang, Huang, *Longitudinal structure of the QGP from differently shaped nuclei*, arXiv:2405.08749 | 预印本，许可未确认 | arXiv 下载 PDF |
| T3-04/05/06 | Kharzeev & Liao, *Chiral magnetic effect reveals the topology of gauge fields in heavy-ion collisions*, **Nat. Rev. Phys. 3**, 55 (2021) | 版权保留 | 机构订阅 |
| T3-07/08 | STAR Collaboration, *Pattern of Global Spin Alignment of φ and K*⁰ mesons in Heavy-Ion Collisions*, **Nature 614**, 244 (2023) | 非 CC-BY | 机构订阅 / arXiv:2204.02302 |

> arXiv 版本通常可自由下载。用 `extract_figures.py` 从 PDF 自动切图：
> ```bash
> python3 scripts/extract_figures.py paper.pdf -o refs/
> ```

## 其他文件

`assets/ir/` 下的 IR 标准答案（YAML）是**本项目的原创工作**，
由分析上述图后独立撰写，不包含原图内容，采用 MIT 许可。

## 更广的原则

做配图研究时，把已发表论文的图当作**风格参考**是常规做法，但
**再分发**要看清许可：

- **CC-BY** → 可再分发，需署名
- **CC-BY-NC / 版权保留** → 内部研究可用，不要再分发
- **arXiv** → 看具体论文的许可声明

`scripts/check_tools.py` 不管这事，但 `SKILL.md` 里有一条相关纪律：
**别把有版权的图直接打包发布。**
