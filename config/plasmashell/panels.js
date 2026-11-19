// macOS-style panels: a menu bar at the top, a dock at the bottom.
// Run by ./apply through plasmashell's scripting API (evaluateScript), only
// while there is no top panel, so later changes made by hand are kept.

// The old bottom panel becomes the dock: only the task manager stays, so its
// pinned launchers survive.
let dock = panels().find(p => p.location == "bottom");
let clockPlugins = "";
if (dock) {
    for (const w of dock.widgets()) {
        if (w.type == "org.kde.plasma.digitalclock") {
            w.currentConfigGroup = ["Appearance"];
            clockPlugins = w.readConfig("enabledCalendarPlugins", "");
        }
        if (w.type != "org.kde.plasma.icontasks") w.remove();
    }
} else {
    dock = new Panel;
    dock.location = "bottom";
}
if (dock.widgets().length == 0) dock.addWidget("org.kde.plasma.icontasks");
dock.height = 2 * Math.ceil(gridUnit * 2.5 / 2);
dock.alignment = "center";
dock.lengthMode = "fit";
dock.floating = true;
dock.hiding = "dodgewindows";           // hides only when a window touches it

// The menu bar: start menu, the focused app's menus, the topdo badge, then tray and clock.
const bar = new Panel;
bar.location = "top";
bar.height = Math.round(gridUnit * 1.5);
bar.floating = false;
const kickoff = bar.addWidget("org.kde.plasma.kickoff");
kickoff.currentConfigGroup = ["General"];
kickoff.writeConfig("icon", "start-here-branding");
bar.addWidget("org.kde.plasma.appmenu");
const topdo = bar.addWidget("io.github.wangji20.topdo");  // the todo badge; fills the middle and centres itself
topdo.globalShortcut = "Meta+Space";                        // opens its panel (Meta+T is KWin's tiles editor)
bar.addWidget("org.kde.plasma.systemtray");
const clock = bar.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateDisplayFormat", "BesideTime");
if (clockPlugins) clock.writeConfig("enabledCalendarPlugins", clockPlugins);
