# tools

数据来自站点前端 bundle，重新抓取步骤：

1. 下载 bundle：`https://cn.ark-nights.com/bundle.bbf8f.esm.js`
2. 用 webpack 运行时装模块，导出：干员（含 elites/skills/master_skills/equipments）、
   材料（含合成 formula）、等级成本表（maxLevel / upgradeCoin / upgradeExp）、
   Ovxt 常量（龙门币/经验/作战记录）。
3. 存成 `data/*.json`，再运行 `python app/build_db.py` 重建 `app/arknights.db`。

`data/availability.json` 标记哪些干员不可培养（预备干员 / 卫戍协议等特殊模式专用）。

材料物品 id 映射：官方 `item_table.json` → `data/items_map.json`。
干员头像：PRTS `文件:头像 <干员名>.png`，缩放到 96px 存 `app/icons/operators/<char_id>.png`。
