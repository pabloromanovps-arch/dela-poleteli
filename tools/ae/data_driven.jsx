// Генерация версий из таблицы: TPL_<шаблон> × строки CSV → OUT_<шаблон>_<id> + очередь рендера.
// Запуск:
//   python tools/run.py ae-script tools/ae/data_driven.jsx --args project=<aep> template=TPL_players
//       csv=data/players.csv render=1 om=DP_ProRes4444 out=projects/<id>/08_delivery/players
// Контракт слоёв (скилл data-driven-templates):
//   @колонка — текст / футаж / цвет (эффект Fill или Color Control);
//   на нуле CTRL_data слайдеры ctrl_<имя> ← колонки ctrl_<имя>;
//   комментарий слоя "fit:<maxWidthPx>,<minScale%>" — ужатие длинного текста.
#include "lib/dp.jsxinc"
DP.init(File($.fileName));

(function () {
    var a = DP.args;
    if (a.project && !DP.open(a.project)) { DP.log("Проект не найден, работаем в открытом: " + a.project); }
    var tpl = DP.findComp(a.template);
    if (!tpl) { throw new Error("Нет шаблона " + a.template); }
    var csvFile = new File(DP.path(a.csv));
    var rows = DP.parseCSV(DP.readText(csvFile));
    var dataDir = csvFile.parent.fsName;
    var folders = DP.ensureFolders();
    var base = a.template.replace(/^TPL_/, "");
    var outDir = a.out || ("tools/.run/out/" + base);
    var made = 0, errors = 0;

    app.beginUndoGroup("DP data_driven");
    for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        if (row.skip === "1") { continue; }
        if (!row.id) { DP.log("Строка " + (r + 2) + ": нет id — пропуск"); errors++; continue; }
        try {
            var name = "OUT_" + base + "_" + row.id;
            var old = DP.findComp(name);
            if (old) { old.remove(); }
            var comp = tpl.duplicate();
            comp.name = name;
            comp.parentFolder = folders["05_RENDER"];
            if (row.dur) { comp.duration = parseFloat(row.dur); comp.workAreaDuration = comp.duration; }
            applyRow(comp, row, dataDir, folders["04_ASSETS"]);
            if (a.render === "1") { DP.queue(comp, a.om, outDir); }
            made++;
        } catch (e) {
            errors++;
            DP.log("ОШИБКА в строке id=" + row.id + ": " + e.toString() + " (line " + e.line + ")");
        }
    }
    app.endUndoGroup();

    if (a.project) { DP.save(a.project); }
    DP.log("Готово: версий " + made + ", ошибок " + errors);
})();

function applyRow(comp, row, dataDir, assetFolder) {
    for (var i = 1; i <= comp.numLayers; i++) {
        var layer = comp.layer(i);
        if (layer.name === "CTRL_data") { applyControls(layer, row); continue; }
        if (layer.name.charAt(0) !== "@") { continue; }
        var col = layer.name.substring(1);
        if (!row.hasOwnProperty(col) || row[col] === "") { continue; }
        var val = row[col];

        if (layer instanceof TextLayer) {
            DP.setText(layer, val);
            var m = /fit:(\d+),(\d+)/.exec(layer.comment);
            if (m) { DP.fitText(layer, parseInt(m[1], 10), parseInt(m[2], 10)); }
        } else if (/^#?[0-9a-fA-F]{6}$/.test(val)) {
            setColor(layer, DP.hex(val));
        } else if (layer instanceof AVLayer) {
            var path = /^[A-Za-z]:|^\//.test(val) ? val : dataDir + "/" + val;
            layer.replaceSource(DP.importFile(path, assetFolder), false);
        }
    }
}

function setColor(layer, rgb) {
    var fx = layer.property("ADBE Effect Parade");
    for (var j = 1; j <= fx.numProperties; j++) {
        var e = fx.property(j);
        if (e.matchName === "ADBE Fill") { e.property("ADBE Fill-0002").setValue(rgb); return; }
        if (e.matchName === "ADBE Color Control") { e.property(1).setValue(rgb); return; }
    }
    DP.log("Слой " + layer.name + ": нет эффекта Fill/Color Control для цвета");
}

function applyControls(layer, row) {
    var fx = layer.property("ADBE Effect Parade");
    for (var k in row) {
        if (!row.hasOwnProperty(k) || k.indexOf("ctrl_") !== 0 || row[k] === "") { continue; }
        var e = fx.property(k);
        if (e) { e.property(1).setValue(parseFloat(row[k])); }
    }
}
