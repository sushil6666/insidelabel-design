# D-186: crop a pack picture to the pack, on /review

Before and after, taken from the app run from this branch with a made-up front photo (a red "Premia Jeera
100 g" pack in a hand over a tiled floor). "After" shows a box dragged round the pack and the
"What will be shown" preview beside it.

| File | Screen | Width | Theme |
|---|---|---|---|
| before-item-*, after-item-* | the pack picture block on a review item | 1280, 390 | light, dark |
| before-pictures-*, after-pictures-* | /review/pictures, a reviewer's own photo chosen | 1280, 390 | light, dark |

The review item page was already wider than a 390 px phone before this change (the block is 646 px in both).
