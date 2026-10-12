Leaflet (https://leafletjs.com), BSD-2-Clause licence (see LICENSE).

Served from here rather than a CDN so the maps work under the site's
Content-Security-Policy (script-src 'self') and on networks that can't reach CDNs.

leaflet.js   Official Leaflet 1.9.3 build.
             sha256-WBkoXOwTeyKclOHuWtc+i2uENFpDZ9YPdf5Hf+D7ewM=
             (matches integrity_hash_uglified in Leaflet's docs/_config.yml)
leaflet.css  Official Leaflet 1.9.4 stylesheet, from the v1.9.4 git tag.
             sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=
             (matches the official 1.9.4 integrity hash). Its only change from
             1.9.3 is the Chrome tile-gap fix (mix-blend-mode on tiles).
images/      Leaflet 1.9.4 dist images (default marker and layer icons).

Check a file with:  openssl dgst -sha256 -binary leaflet.js | base64
