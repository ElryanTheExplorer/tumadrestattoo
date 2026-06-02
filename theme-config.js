/* Tu Madre's Tattoo — Theme Config
   Generated from admin.html · Replace this file to update site-wide palette.
   All pages load this file in <head> before first paint. */
(function(){
  var theme = "dark";
  var overrides = {};
  /* When Cat customizes individual colors beyond a preset,
     they appear here as {"--rust":"#ff0000",...} etc.
     Empty object = pure preset, no custom tweaks. */
  var r = document.documentElement;
  r.setAttribute("data-theme", theme);
  for (var k in overrides) r.style.setProperty(k, overrides[k]);
})();
