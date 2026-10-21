// Аниматик из раскадровки: board.csv (shot_id,in_s,dur_s,frame,label) → ANIMATIC.
//   python tools/run.py ae-script tools/ae/build_animatic.jsx
//       --args screen=<profile> board=projects/<id>/04_board/board.csv project=projects/<id>/04_board/animatic.aep
// frame — путь к стайлфрейму (относительно board.csv); пусто → серая плашка.
#include "lib/dp.jsxinc"
#include "lib/easing.jsxinc"
DP.init(File($.fileName));

(function () {
    var a = DP.args, s = DP.screen();
    var boardFile = new File(DP.path(a.board));
    var shots = DP.parseCSV(DP.readText(boardFile));
    var total = 0, i;
    for (i = 0; i < shots.length; i++) { total = Math.max(total, parseFloat(shots[i].in_s) + parseFloat(shots[i].dur_s)); }
    var folders = DP.ensureFolders();
    app.beginUndoGroup("DP animatic");
    var comp = DP.compFromScreen("ANIMATIC", total, folders["00_MASTER"]);
    var W = comp.width, H = comp.height;

    for (i = shots.length - 1; i >= 0; i--) {
        var sh = shots[i], t0 = parseFloat(sh.in_s), d = parseFloat(sh.dur_s), layer;
        if (sh.frame) {
            layer = comp.layers.add(DP.importFile(boardFile.parent.fsName + "/" + sh.frame, folders["99_REF"]));
            var sc = Math.max(W / layer.width, H / layer.height) * 100;
            DPE.animate(layer.property("ADBE Transform Group").property("ADBE Scale"),
                [[t0, [sc, sc]], [t0 + d, [sc * 1.04, sc * 1.04]]], "cinematic");
        } else {
            layer = comp.layers.addSolid([0.2, 0.2, 0.22], sh.shot_id, W, H, 1, d);
        }
        layer.startTime = t0;
        layer.inPoint = t0;
        layer.outPoint = t0 + d;
        var label = comp.layers.addText(sh.shot_id + "  " + (sh.label || ""));
        var p = label.property("ADBE Text Properties").property("ADBE Text Document"), doc = p.value;
        doc.fontSize = Math.round(H * 0.025); doc.fillColor = [1, 1, 0.3]; doc.applyFill = true;
        p.setValue(doc);
        label.property("ADBE Transform Group").property("ADBE Position").setValue([W * 0.03, H * 0.95]);
        label.inPoint = t0; label.outPoint = t0 + d;
        label.guideLayer = false;
    }
    var tc = comp.layers.addText("");
    tc.name = "TC";
    tc.property("ADBE Text Properties").property("ADBE Text Document").expression = "timeToTimecode(time)";
    tc.property("ADBE Transform Group").property("ADBE Position").setValue([W * 0.85, H * 0.95]);

    app.endUndoGroup();
    if (a.project) { DP.save(a.project); }
    DP.log("Аниматик: шотов " + shots.length + ", " + total + " c");
})();
