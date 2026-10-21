// Демо-шаблон заставки игрока TPL_players — пилот пайплайна «таблица → версии».
// Строит проект с нуля по профилю экрана:
//   python tools/run.py ae-script tools/ae/demo_players_template.jsx
//       --args screen=uhd_16x9 project=projects/demo/06_build/players.aep
// Затем: data_driven.jsx с csv=examples/players/players.csv
#include "lib/dp.jsxinc"
#include "lib/easing.jsxinc"
DP.init(File($.fileName));

(function () {
    app.newProject();
    var s = DP.screen(), W = s.canvas.width, H = s.canvas.height, fps = s.fps;
    var folders = DP.ensureFolders();
    var DUR = 6, f = 1 / fps;
    app.beginUndoGroup("DP demo template");

    var comp = DP.ensureComp("TPL_players", W, H, DUR, fps, folders["03_TEMPLATES"]);
    comp.bgColor = [0.02, 0.02, 0.03];

    // Контроллер данных (слайдер ctrl_speed — общий темп)
    var ctrl = comp.layers.addNull(DUR);
    ctrl.name = "CTRL_data";
    ctrl.property("ADBE Effect Parade").addProperty("ADBE Slider Control").name = "ctrl_speed";
    ctrl.property("ADBE Effect Parade").property("ctrl_speed").property(1).setValue(1);
    ctrl.enabled = false;

    // Цвет команды: полоса-акцент с эффектом Fill
    var bar = comp.layers.addSolid([1, 1, 1], "@team_color", Math.round(W * 0.012), Math.round(H * 0.42), 1, DUR);
    bar.property("ADBE Effect Parade").addProperty("ADBE Fill");
    bar.property("ADBE Effect Parade").property(1).property("ADBE Fill-0002").setValue([0.9, 0.1, 0.15]);
    bar.property("ADBE Transform Group").property("ADBE Position").setValue([W * 0.12, H * 0.55]);
    DPE.animate(bar.property("ADBE Transform Group").property("ADBE Scale"),
        [[0.2, [100, 0]], [0.2 + 18 * f, [100, 100]]], "precise");

    // Фото игрока (заглушка; заменится файлом из колонки photo)
    var photo = comp.layers.addSolid([0.15, 0.15, 0.18], "@photo", Math.round(H * 0.7), Math.round(H * 0.85), 1, DUR);
    photo.property("ADBE Transform Group").property("ADBE Position").setValue([W * 0.72, H * 0.575]);
    DPE.animate(photo.property("ADBE Transform Group").property("ADBE Opacity"),
        [[0.3, 0], [0.3 + 20 * f, 100]], "soft");
    DPE.animate(photo.property("ADBE Transform Group").property("ADBE Scale"),
        [[0.3, [106, 106]], [DUR, [100, 100]]], "cinematic");

    // Тексты
    function txt(name, size, x, y, delay, fit) {
        var l = comp.layers.addText(name.substring(1).toUpperCase());
        l.name = name;
        var p = l.property("ADBE Text Properties").property("ADBE Text Document"), d = p.value;
        d.fontSize = size; d.fillColor = [1, 1, 1]; d.applyFill = true; d.justification = ParagraphJustification.LEFT_JUSTIFY;
        d.tracking = -10;
        p.setValue(d);
        if (fit) { l.comment = "fit:" + fit + ",55"; }
        var pos = l.property("ADBE Transform Group").property("ADBE Position");
        DPE.animate(pos, [[delay, [x, y + size * 0.4]], [delay + 18 * f, [x, y]]], "confident");
        DPE.animate(l.property("ADBE Transform Group").property("ADBE Opacity"), [[delay, 0], [delay + 10 * f, 100]], "enter");
        return l;
    }
    txt("@number", Math.round(H * 0.2), W * 0.15, H * 0.42, 0.35);
    txt("@name", Math.round(H * 0.09), W * 0.15, H * 0.6, 0.45, Math.round(W * 0.45));
    txt("@position", Math.round(H * 0.035), W * 0.15, H * 0.68, 0.55);

    app.endUndoGroup();
    if (DP.args.project) { DP.save(DP.args.project); }
    DP.log("TPL_players собран: " + W + "x" + H + " @" + fps);
})();
