# 图层清单 — jet_quenching.svg

图层树：`面板 panel` → `物理元素 element` → `<path>`。
★ 图层只按【物理元素】分，**不按颜色分层** —— 人打开图层面板看到的应该是
物理（nucleus-A / photon-B / arrow-b…），不是 white / orange / gray。
同色矩形仍会并成一条 path（那只是体积优化），颜色挂在 `data-color` 上；
要把一个元素再拆成子结构（如 `nucleus-A-body` / `nucleus-A-outline`），用 `panels.py` 的 `SPLIT` 显式写，而不是靠自动的颜色分组。
在 Illustrator 里打开「图层」面板即可按下面的名字点选；在 Inkscape 里是子图层。

| 面板 | 物理元素 | 说明 | 包围盒 (x0,y0,x1,y1) | 路径数 | 像素 |
|---|---|---|---|---|---|
| `p` | `p-background` | Panel background (white) | 0,0,1662,926 | 146 | 1206215 |
| `p` | `p-medium` | QGP medium: vertically elongated semi-transparent ellipsoid (long axis = beam direction, vertical) | 622,44,1080,816 | 20112 | 229963 |
| `p` | `p-vertex` | Hard-scattering starburst (bright yellow-white) at the dijet origin | 921,345,1052,423 | 430 | 1184 |
| `p` | `p-jet-unquenched-cone` | Unquenched jet: collimated cone going up-right. Short path -- it leaves the medium almost immediately, so it stays bright and saturated | 956,80,1355,415 | 3267 | 32729 |
| `p` | `p-jet-unquenched-hadrons` | Hadron cluster at the tip of the unquenched jet (many, bright, light blue) | 1240,109,1341,209 | 664 | 5308 |
| `p` | `p-jet-quenched-cone` | Quenched jet: cone going down-left. Long path -- it traverses nearly the whole medium, so it is desaturated, grey-blue and fades out | 291,404,927,767 | 2642 | 24224 |
| `p` | `p-jet-quenched-hadrons` | Hadron cluster at the tip of the quenched jet (only 2-3, darker, grey) | 289,161,1293,710 | 2271 | 16581 |
| `p` | `p-gluon-radiation` | Gluon bremsstrahlung: small yellow-green dots and swirls along the quenched jet, only inside the medium (this is the energy-loss mechanism) | 694,386,984,568 | 4382 | 22161 |
| `p` | `p-beam-arrow` | Beam direction: short vertical double-headed arrow in the gap right of the medium | 1064,562,1080,682 | 162 | 647 |
| `p` | `p-text` | text layer (6 editable <text>) | - | 6 | - |

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
