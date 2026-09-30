/** Vector rendition of the supplied blue/grey wave for shallow workspace footers.
 * The browser rasterizes these curves at the current screen resolution and zoom.
 * Coordinates describe the final shallow band, rather than compressing a PNG.
 */
export function BrandWave() {
  return <svg className="hrms-workspace-wave" viewBox="0 0 1600 48" preserveAspectRatio="none" aria-hidden="true" focusable="false">
    <path fill="#d9d9d9" d="M0 22C180 8 320 6 520 17S900 42 1160 31S1450 16 1600 8V25C1420 40 1280 46 1080 39S650 20 420 21S140 33 0 42Z" />
    <path fill="#0047ab" d="M0 34C230 11 370 0 590 7S890 32 1130 30S1460 24 1600 7V34C1370 49 1230 50 1010 41S660 16 410 24S160 32 0 45Z" />
    <path fill="#7a9bc9" d="M0 28C210 2 330 10 570 18S920 39 1130 33S1450 28 1600 11V29C1390 39 1230 41 1050 34S630 19 410 22S130 37 0 42Z" />
    <path fill="#638ac0" d="M0 33C180 17 330 14 540 17S920 36 1130 34S1450 26 1600 16V29C1400 38 1270 42 1050 35S680 21 450 25S180 36 0 44Z" />
    <path fill="#d9d9d9" d="M0 42C210 25 390 16 590 20S920 43 1150 38S1460 24 1600 19V31C1390 42 1260 47 1060 42S700 26 470 29S160 35 0 46Z" />
    <path fill="#1955ac" d="M0 44C210 25 360 26 580 32S960 49 1170 42S1470 27 1600 14V34C1390 46 1240 50 1040 46S690 30 460 30S170 34 0 47Z" />
  </svg>;
}
