// Бит-сетка (tools/audio/beats.py) → маркеры и огибающая в композиции.
//   python tools/run.py ae-script tools/ae/import_beatgrid.jsx
//       --args project=<aep> comp=MASTER_uhd beatgrid=projects/<id>/04_board/beatgrid.json audio=<wav>
// Создаёт нуль CTRL_audio: маркеры (bar N / секции), слайдер env (0..1) с ключами громкости.
// В выражениях: thisComp.layer("CTRL_audio").effect("env")("Slider")
#include "lib/dp.jsxinc"
DP.init(File($.fileName));

(function () {
    var a = DP.args;
    if (a.project) { DP.open(a.project); }
    var comp = DP.findComp(a.comp);
    if (!comp) { throw new Error("Нет композиции " + a.comp); }
    var grid = DP.json.parse(DP.readText(new File(DP.path(a.beatgrid))));
    app.beginUndoGroup("DP beatgrid");

    var old = comp.layers.byName("CTRL_audio");
    if (old) { old.remove(); }
    if (a.audio) {
        var au = comp.layers.add(DP.importFile(a.audio, DP.ensureFolders()["04_ASSETS"]));
        au.name = "AUDIO_track";
    }
    var ctrl = comp.layers.addNull(comp.duration);
    ctrl.name = "CTRL_audio";
    ctrl.enabled = false;

    var markers = ctrl.property("ADBE Marker"), i, mv;
    var beats = a.marks === "beats" ? grid.beats : grid.downbeats;
    for (i = 0; i < beats.length; i++) {
        if (beats[i] > comp.duration) { break; }
        mv = new MarkerValue(a.marks === "beats" ? String(i + 1) : "bar " + (i + 1));
        markers.setValueAtTime(beats[i], mv);
    }
    for (i = 0; i < grid.sections.length; i++) {
        mv = new MarkerValue("SECTION " + (i + 1));
        mv.label = 1;
        markers.setValueAtTime(grid.sections[i] + 0.0001, mv);
    }

    var env = ctrl.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
    env.name = "env";
    var times = [], vals = [];
    for (i = 0; i < grid.envelope.times.length; i++) {
        if (grid.envelope.times[i] > comp.duration) { break; }
        times.push(grid.envelope.times[i]);
        vals.push(grid.envelope.values[i]);
    }
    env.property(1).setValuesAtTimes(times, vals);

    app.endUndoGroup();
    if (a.project) { DP.save(a.project); }
    DP.log("Бит-сетка: темп " + grid.tempo + " BPM, тактов " + grid.downbeats.length);
})();
