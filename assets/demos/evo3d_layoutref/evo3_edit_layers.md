# 图层清单 — evo3_edit.svg

图层树：`面板 panel` → `物理元素 element` → `<path>`。
★ 图层只按【物理元素】分，**不按颜色分层** —— 人打开图层面板看到的应该是
物理（nucleus-A / photon-B / arrow-b…），不是 white / orange / gray。
同色矩形仍会并成一条 path（那只是体积优化），颜色挂在 `data-color` 上；
要把一个元素再拆成子结构（如 `nucleus-A-body` / `nucleus-A-outline`），用 `panels.py` 的 `SPLIT` 显式写，而不是靠自动的颜色分组。
在 Illustrator 里打开「图层」面板即可按下面的名字点选；在 Inkscape 里是子图层。

| 面板 | 物理元素 | 说明 | 包围盒 (x0,y0,x1,y1) | 路径数 | 像素 |
|---|---|---|---|---|---|
| `p` | `p-background` | Panel background (white) | 0,0,1664,928 | 131 | 1258507 |
| `p` | `p-stage1-nucleus` | Stage 1: one deformed nucleus (tilted ellipsoid with surface mesh) + 基色x2 + 明度层（残差 0.95） | 39,259,258,588 | 59 | 56253 |
| `p` | `p-stage2-fluctuations` | Stage 2: quantum fluctuations -- the same nucleus in three orientations (three overlapping ellipses) + 基色x2 + 明度层（残差 0.89） | 372,256,712,569 | 57 | 71962 |
| `p` | `p-stage3-nucleus-A` | Stage 3: projectile nucleus A, left lobe of the colliding pair + 基色x3 + 明度层（残差 1.02） | 812,328,1037,515 | 58 | 28252 |
| `p` | `p-stage3-nucleus-B` | Stage 3: target nucleus B, right lobe of the colliding pair + 基色x1 + 明度层（残差 1.98） | 966,336,1189,516 | 56 | 24907 |
| `p` | `p-stage4-fireball` | Stage 4: QGP fireball (orange radial-gradient disc) | 1294,243,1636,597 | 17297 | 87203 |
| `p` | `p-arrow-1` | Evolution arrow 1 (stage 1 -> 2, thick, pointing right) + 基色x3 + 明度层（残差 1.07） | 283,407,1113,512 | 51 | 3395 |
| `p` | `p-arrow-2` | Evolution arrow 2 (stage 2 -> 3, thick, pointing right) + 基色x2 + 明度层（残差 0.72） | 721,408,797,462 | 41 | 1738 |
| `p` | `p-arrow-3` | Evolution arrow 3 (stage 3 -> 4, thick, pointing right) + 基色x2 + 明度层（残差 0.61） | 1201,407,1278,462 | 47 | 1755 |
| `p` | `p-stage4-nucleons` | Stage 4: nucleon cluster in the fireball core (glow split off by radius) | 1412,368,1517,472 | 3328 | 8445 |
| `p` | `p-stage3-overlap` | Stage 3: overlapping (participating) matter -- vertical lens + 基色x2 + 明度层（残差 1.72） | 968,401,1004,483 | 26 | 1775 |
| `p` | `p-text` | text layer (5 editable <text>) | - | 5 | - |

## 怎么改

- 改某个物理内容（火球 / 核子 / 流箭头 / 曲面 / 坐标轴 / 介质管…）：选中对应 `panel-element` 图层改颜色或形状。
- 改文字：选中 `panel-text` 里的真 `<text>`，字体、字号、内容都可直接编辑。
- 要重命名/调整元素范围：编辑 `panels.py` 的 `ELEMENTS`（框 + 颜色条件）与 `SPLIT`，再重跑 groupvec.py。
- 元素名字带「+ 真X渐变 body + 明度层」的：该元素的整体颜色就是一条真渐变，
  改 <defs> 里那条 gradient 的 stop 即整体改色；明暗层是黑/白 + fill-opacity，
- 元素名字带「+ 基色xN + 明度层」的：N 个基色块各有一个 fill（整体改色的把手），
  明暗层是黑/白 + fill-opacity（不含颜色），换基色时明暗关系自动跟着走。
- 元素名字带「+ 真 radialGradient/linearGradient」的：该元素的大片平滑渐变已
  合并成一条 `data-role="gradient-shape"` 的 path（渐变定义在文件末尾的 `<defs>`），
  底色台阶已丢掉；改渐变色/中心就在 `<defs>` 里改那个 gradient。
