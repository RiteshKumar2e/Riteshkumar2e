# Third-party assets and licenses

All five SVGs in this folder embed their fonts and images as data URIs. Rendering them makes no network requests.

## Fonts (embedded as subset WOFF2)

| Font | Weights | License | Source |
| --- | --- | --- | --- |
| Space Grotesk (display) | 500, 700 | SIL Open Font License 1.1, see `OFL-SpaceGrotesk.txt` | https://github.com/floriankarsten/space-grotesk via @fontsource/space-grotesk 5.3.0 |
| JetBrains Mono (mono) | 500, 700 | SIL Open Font License 1.1, see `OFL-JetBrainsMono.txt` | https://github.com/JetBrains/JetBrainsMono via @fontsource/jetbrains-mono 5.3.0 |

The fonts are subset to the characters each SVG uses. The OFL allows embedding and subsetting. The embedded fonts keep their original names, copyright notices and license strings.

## Icons

Brand icons come from **Simple Icons 16.34.0** (https://simpleicons.org, npm `simple-icons`). The icon data is released under **CC0 1.0**, see `LICENSE-simple-icons.md`. The brands themselves remain trademarks of their owners, and the icons are used here only to identify each technology or platform.

| Label | Simple Icons title | Colour | Upstream source (from Simple Icons metadata) |
| --- | --- | --- | --- |
| Python | Python | #3776AB | https://www.python.org/community/logos/ |
| C++ | C++ | #00599C | https://github.com/isocpp/logos/tree/64ef037049f87ac74875dbe72695e59118b52186 |
| TensorFlow | TensorFlow | #FF6F00 | https://www.tensorflow.org |
| PyTorch | PyTorch | #EE4C2C | https://github.com/pytorch/pytorch.github.io/blob/8f083bd12192ca12d5e1c1f3d236f4831d823d8f/assets/images/logo.svg |
| Keras | Keras | #D00000 | https://keras.io |
| OpenCV | OpenCV | #5C3EE8 | https://opencv.org/resources/media-kit/ |
| Scikit-learn | scikit-learn | #F7931E | https://github.com/scikit-learn/scikit-learn/blob/c5ef2e985c13119001aa697e446ebb3dbcb326e5/doc/logos/scikit-learn-logo.svg |
| NumPy | NumPy | #013243 | https://numpy.org/press-kit/ |
| Pandas | pandas | #150458 | https://pandas.pydata.org/about/citing.html |
| FastAPI | FastAPI | #009688 | https://github.com/tiangolo/fastapi/blob/ffb4f77a11f83132b521ba0aac6c95792c19e797/docs/en/docs/img/icon-white.svg |
| Node.js | Node.js | #5FA04E | https://nodejs.org/en/about/branding |
| Express.js | Express | #0A0A0A | https://github.com/openjs-foundation/artwork/blob/3816245ebbf4707bdafde748350ac8476b6b5b62/projects/express/express-icon-black.svg |
| React | React | #61DAFB | https://github.com/facebook/create-react-app/blob/282c03f9525fdf8061ffa1ec50dce89296d916bd/test/fixtures/relative-paths/src/logo.svg |
| REST APIs | — | — | Generic braces glyph drawn for this profile (not a brand mark) |
| MongoDB | MongoDB | #47A248 | https://www.mongodb.com/pressroom |
| MySQL | MySQL | #4479A1 | https://www.mysql.com/about/legal/logos.html |
| PostgreSQL | PostgreSQL | #4169E1 | https://wiki.postgresql.org/wiki/Logo |
| Docker | Docker | #2496ED | https://www.docker.com/company/newsroom/media-resources |
| Git | Git | #F03C2E | https://git-scm.com/community/logos |
| GitHub (connect) | GitHub | #181717 | https://github.com/logos |
| Email (connect) | Gmail | #EA4335 | https://fonts.gstatic.com/s/i/productlogos/gmail_2020q4/v8/192px.svg |

* **Git logo:** by Jason Long, licensed under **CC BY 3.0** (https://git-scm.com/downloads/logos).
* **LinkedIn:** Simple Icons no longer ships a LinkedIn icon. The connect card uses LinkedIn's official "In" bug, `LI-In-Bug.png`, unmodified apart from resizing. It comes from the `in-logo.zip` package on LinkedIn's brand site, https://brand.linkedin.com/downloads, downloaded 07 Oct 2026. LinkedIn and the In logo are trademarks of LinkedIn Corporation. Use follows https://brand.linkedin.com/policies.
* **Other glyphs:** the pin, flask, building, globe, arrow, chevron and braces glyphs are simple line drawings made for this profile.

## Photos

`id.png` and `right_pointing.png` are the profile owner's own images. They are embedded unmodified apart from resizing and, for the pointing photo, cropping. `id.png` keeps its original alpha channel. `right_pointing.png` has no alpha channel, so it is shown in a rounded photo frame exactly as supplied.
