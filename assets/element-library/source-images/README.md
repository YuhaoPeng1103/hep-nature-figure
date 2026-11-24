# Source images

These images are retained solely to make element extraction reproducible. They
are CC BY 4.0 and are not content templates.

| File | Source | Processing |
|---|---|---|
| `PMC12521530_fig2_3701x3352.png` | STAR Collaboration, *Temperature measurement of Quark-Gluon plasma at different stages*, Nature Communications 16 (2025), [10.1038/s41467-025-63216-5](https://doi.org/10.1038/s41467-025-63216-5) | CC BY PDF fig. 2 rendered at 600 dpi; detector, track bundle and vertex crops |
| `PMC13004930_fig1_2683x1752.png` | ALICE Collaboration, *Observation of partonic flow in proton-proton and proton-nucleus collisions*, Nature Communications 17 (2026), [10.1038/s41467-025-67795-1](https://doi.org/10.1038/s41467-025-67795-1) | CC BY PDF fig. 1 rendered at 600 dpi; vector medium preserved; parton-pair crops |
| `PMC7010749_fig1_1694x719.png` | Guo, Liao & Wang, *Spin Hydrodynamic Generation in the Charged Subatomic Swirl*, Scientific Reports 10 (2020), [10.1038/s41598-020-59129-6](https://doi.org/10.1038/s41598-020-59129-6) | CC BY PDF fig. 1 rendered at 600 dpi; vortex ring crops |
| `PMC8913752_fig1_1655x1644.png` | Prasad et al., *Event topology and global observables in heavy-ion collisions at the Large Hadron Collider*, Scientific Reports 12 (2022), [10.1038/s41598-022-07547-z](https://doi.org/10.1038/s41598-022-07547-z) | CC BY PDF fig. 1 rendered at 600 dpi; event-cone and topology crops |
| `T3-11_fig1_1341x983.png` | CMS Collaboration, *Elliptic anisotropy measurement of the f0(980) hadron...*, Nature Communications 16 (2025), [10.1038/s41467-025-56200-6](https://doi.org/10.1038/s41467-025-56200-6) | publisher full-size Fig. 1 |
| `T3-12_fig1_1351x932.png` | ALICE Collaboration, *Observation of partonic flow in proton-proton and proton-nucleus collisions*, Nature Communications 17 (2026), [10.1038/s41467-025-67795-1](https://doi.org/10.1038/s41467-025-67795-1) | publisher full-size Fig. 1 |
| `T3-35_fig12_p30_2339x2047.png` | Xu-Guang Huang, *Electromagnetic fields and anomalous transports in heavy-ion collisions*, [arXiv:1509.04073v3](https://arxiv.org/abs/1509.04073) | Fig. 12, p. 30, rendered at 800 dpi; the PDF-embedded source raster is only 559×485, so individual-nucleon detail has a hard resolution limit |

License text: <https://creativecommons.org/licenses/by/4.0/>.

Element records in `../index.json` preserve the exact crop boxes and source
hashes. Re-extraction:

```bash
python scripts/source_element_extract.py \
  assets/element-library/source-elements.json --replace --prune
```
