# Regali: codici presente e dischi della piazza Wi-Fi

Fonti esterne (consultate il 2026-11-02):
- codici: [Game8, プレゼントコード一覧](https://game8.jp/dqmj3pro/122320) (14 codici speciali DQMJ3P e 100 di DQMJ3, divisi in 特賞 / 1等賞 / 2等賞 / 3等賞);
- distribuzioni: [Game8, Wi-Fi配信モンスター一覧](https://game8.jp/dqmj3pro/123962), [kyokugen.info](https://kyokugen.info/dqmj3/dqmj3professional_before13.html).

[V] = verificato nel codice o nei file del gioco, [G] = dalle guide, [I] = ipotesi.

## 1. Codici presente

### Come li controlla il gioco [V]
- La tabella `data/PresentCode/PresentCodeROMCode.bin` (AES-128-CTR, chiave `90bc1182e5aaf96d55752cf7be4bfcd9`, contatore iniziale `d0733b8cdbdbc0e3a9c6950ef8025561`, entrambi come scritti, poi testo cp932) ha 115 voci `TABLE_ROMCODE_NNN <- { id = N code = "..." }`. Il commento in testa dice che sono codici fissi, validi anche senza Wi-Fi.
- Voci vere: 1-36, 50-64 e, nel RomFS dell'aggiornamento, 80-83. Le altre sono segnaposto `熙NNN`.
- Un codice trovato nella tabella da' il pacchetto locale `PresentCodePackageR%03d.bin`. Un codice sconosciuto va al server SIL (`present_code.bin`, `re/notes/sil_protocol.md` 5.2), che risponde con il numero di un pacchetto `PresentCodePackageS%02u.bin` da scaricare (formato in `re/notes/grandprix_formats.md` 5).

### Da dove vengono i codici [V+G]
- **1-25**: codici "S" di DQMJ3 (特賞 di Game8, stessi numeri), rimasti nella tabella di DQMJ3P.
- **26-35, 80-83**: i 14 codici speciali di DQMJ3P, pubblicati uno a settimana dal 24 febbraio 2017. I numeri 5, 6, 13 e 14 di Game8 (80-83) arrivano con gli aggiornamenti 1.1 e 1.2.
- **36**: `Pu地2トA:Eト` ("puchitto eito"), disco di プチットⅧ (specie 0x364). Non e' nell'elenco di Game8.
- **50-64**: frasi come `げんきだまほしい` (Sfera di Luce ×3), `しあわせのタネほしい` (×5), `しもふりにくほしいな` (×1). Non sono nell'elenco di Game8.
- **26-100 di DQMJ3**: codici A, B e C. DQMJ3P li ha tolti dalla tabella (segnaposto), ma i pacchetti R037-R049, R065-R079 e R084-R100 contengono ancora i loro regali, uguali all'elenco di Game8. I numeri 26-36, 50-64 e 80-83 di DQMJ3 sono stati riusati da DQMJ3P: i loro regali vengono solo da Game8.
- I pacchetti dei segnaposto sono da 80 byte con `0xfc` prima della HMAC: con la dimensione attesa di 0x48 la firma non torna, quindi il gioco non li puo' usare.
- R101-R115 (Sfera di Luce ×3, Semi della Felicita' ×5, Bocconi Bestiali ×1) non hanno un codice noto.

### Sul nostro server
- `re/tools/make_present_codes.py` legge tabella e pacchetti dal RomFS e dall'aggiornamento, aggiunge i codici di Game8 e scrive `server/sil/present_codes.json`. `sil_server.py` lo carica all'avvio.
- Numeri di pacchetto: 200 + numero della tabella, oppure 300 + numero di Game8 per i codici DQMJ3 riusati da DQMJ3P. I pacchetti vengono rifirmati con il proprio numero (stesso corpo degli originali, HMAC chiave 1).
- I codici vengono normalizzati prima del confronto: NFKC (lettere a larghezza piena), `〜` uguale a `～`, maiuscole.
- La tastiera delle traduzioni ha solo lettere, quindi ogni regalo ha anche un **alias**: il nome inglese dell'oggetto senza spazi, piu' la quantita' in parole quando lo stesso oggetto esiste in quantita' diverse. Un alias vale una volta per giocatore, come ogni codice.
- I codici che il giocatore inserisce come sono nella tabella del gioco non arrivano al server: li gestisce il gioco.
- I codici aggiunti a mano nella tabella `present_codes` del database SIL hanno la precedenza.

### Tabella completa

| Pacchetto | Gioco | Codice originale | Regalo | Nome IT | Alias |
|---|---|---|---|---|---|
| 201 | DQMJ3 | `Sゴる王ょ最将神スら` | スライムゴールドのMAP (disco) |  | `GOLDSLIMEDISC` |
| 202 | DQMJ3 | `Sすラ神愛文ぞぽごル` | メタルスライムのMAP (disco) |  | `METALSLIMEDISC` |
| 203 | DQMJ3 | `S全ひ年ケ道作ガ馬ご` | ほねつきにく ×1 | Leccornia carnosa | `MEATYTREAT` |
| 204 | DQMJ3 | `S少丸ツ戦翼心イご斬` | レッドオーブ ×1 | Sfera Rossa | `REDORB` |
| 205 | DQMJ3 | `Sで書将よちぴ火強ジ` | ブルーオーブ ×1 | Sfera Blu | `BLUEORB` |
| 206 | DQMJ3 | `S皇をト最病テス族皇` | イエローオーブ ×1 | Sfera Gialla | `YELLOWORB` |
| 207 | DQMJ3 | `S士力ダ発若ダ船戦デ` | グリーンオーブ ×1 | Sfera Verde | `GREENORB` |
| 208 | DQMJ3 | `Sぁ極バぶ獣封ルム竜` | パープルオーブ ×1 | Sfera Viola | `PURPLEORB` |
| 209 | DQMJ3 | `Sエく眼ヒキ名年丸鬼` | 元気玉 ×1 | Sfera di Luce | `BALLOFLIGHTONE` |
| 210 | DQMJ3 | `S地もぃ宮ぽ右や騎ゥ` | いのちのきのみ ×3 | Seme della Vita | `SEEDOFLIFE` |
| 211 | DQMJ3 | `Sあぽザ人地車鬼ら特` | ふしぎなきのみ ×3 | Seme della Magia | `SEEDOFMAGIC` |
| 212 | DQMJ3 | `Sヲ曹なぼワ長高悪ケ` | ちからのタネ ×3 | Seme della Forza | `SEEDOFSTRENGTH` |
| 213 | DQMJ3 | `S神守師ごハ鳥づコじ` | すばやさのタネ ×3 | Seme dell'Agilità | `SEEDOFAGILITY` |
| 214 | DQMJ3 | `Sぷスぱ究した破赤め` | まもりのタネ ×3 | Seme della Resilienza | `SEEDOFRESILIENCE` |
| 215 | DQMJ3 | `Sセぃの最鳥文じ名ナ` | かしこさのタネ ×3 | Seme della Saggezza | `SEEDOFWISDOM` |
| 216 | DQMJ3 | `Sワゼヤ勇技悪ゼ攻チ` | スキルのタネ ×3 | Semi di Abilità | `SKILLSEEDSTHREE` |
| 217 | DQMJ3 | `S少ガざら裂ロス心あ` | しあわせのタネ ×3 | Semi della Felicità | `SEEDSOFHAPPINESSTHREE` |
| 218 | DQMJ3 | `Sセ竜暗軍り冥じるシ` | メタルストーン ×1 | Flipper | `PINBALL` |
| 219 | DQMJ3 | `S作撃神丸書ゃぼ火ぼ` | ばくだんいし ×1 | Frammento di Esplo-sasso | `ROCKBOMBSHARD` |
| 220 | DQMJ3 | `S士絶ゼモ鳥や死手老` | ばんのうぐすり ×1 | Panacea | `PANACEAONE` |
| 221 | DQMJ3 | `S宮少力ぜ作炎め忍ジ` | 上やくそう ×3 | Medicina potente | `STRONGMEDICINETHREE` |
| 222 | DQMJ3 | `S族書獣火プ霧道雪ボ` | まほうのせいすい ×3 | Acqua magica | `MAGICWATERTHREE` |
| 223 | DQMJ3 | `S心剣望聖ど地老ォ曹` | くんせいにく ×3 | Carne affumicata | `SMOKEDMEAT` |
| 224 | DQMJ3 | `S吹ひ息ギノ黒ッ手マ` | バイキルミン ×3 | Polvere Oomph | `OOMPHPOWDER` |
| 225 | DQMJ3 | `S怪な体ぅぎ書皇右ァ` | スクルティオ ×3 | Bufferina Jumbo | `JUMBOBUFFERINE` |
| 226 | DQMJ3P | `ちョうi♪No地ノ木noミ` | 超いのちのきのみ ×5 | Semi della Vita Grandi | `LARGELIFESEEDS` |
| 227 | DQMJ3P | `長吹姉ぎ名!鬼ノみ` | 超ふしぎなきのみ ×5 | Super Seme della Magia | `SUPERSEEDOFMAGIC` |
| 228 | DQMJ3P | `地Lyo右力Noタ↑ね` | 超ちからのタネ ×5 | Super Seme della Forza | `SUPERSEEDOFSTRENGTH` |
| 229 | DQMJ3P | `チ?ょうSUバ夜左ノTaネ` | 超すばやさのタネ ×5 | Super Seme dell'Agilità | `SUPERSEEDOFAGILITY` |
| 230 | DQMJ3P | `鳥魔mおRe;ノたNe` | 超まもりのタネ ×5 | Super Seme della Resilienza | `SUPERSEEDOFRESILIENCE` |
| 231 | DQMJ3P | `チょ右花士→コ左のTanE` | 超かしこさのタネ ×5 | Super Seme della Saggezza | `SUPERSEEDOFWISDOM` |
| 232 | DQMJ3P | `TY^oウ守死のたnE` | 超スキルのタネ ×10 | Grandi Semi di Abilità | `LARGESKILLSEEDSTEN` |
| 233 | DQMJ3P | `」ちョU使Mo不rE憎火鬼花エ剣` | 超しもふりにく引換券 ×1 | Buono Sirloin | `SIRLOINVOUCHER` |
| 234 | DQMJ3P | `地夜↓右幻木堕魔` | 超元気玉 ×5 | Grande Sfera di Luce | `LARGELIGHTBALL` |
| 235 | DQMJ3P | `使ン樹←右赤` | 神獣石 ×10 | Pietra di Incarnus | `INCARNUSSTONETEN` |
| 236 | DQMJ3P | `Pu地2トA:Eト` | プチットⅧ (disco) |  | `CHIBIEIGHTSDISC` |
| 250 | DQMJ3P | `げんきだまほしい` | 元気玉 ×3 | Sfera di Luce | `BALLOFLIGHTTHREE` |
| 250 | DQMJ3P | `ほしいゲんきだま` | 元気玉 ×3 | Sfera di Luce | `BALLOFLIGHTTHREE` |
| 250 | DQMJ3P | `げんきだまをクださい` | 元気玉 ×3 | Sfera di Luce | `BALLOFLIGHTTHREE` |
| 250 | DQMJ3P | `くだサいげんきだまを` | 元気玉 ×3 | Sfera di Luce | `BALLOFLIGHTTHREE` |
| 250 | DQMJ3P | `ゲんキだマ` | 元気玉 ×3 | Sfera di Luce | `BALLOFLIGHTTHREE` |
| 255 | DQMJ3P | `シあわせのたねほしい` | しあわせのタネ ×5 | Semi della Felicità | `SEEDSOFHAPPINESSFIVE` |
| 255 | DQMJ3P | `ほしいしあわせノたね` | しあわせのタネ ×5 | Semi della Felicità | `SEEDSOFHAPPINESSFIVE` |
| 255 | DQMJ3P | `しあワせをください` | しあわせのタネ ×5 | Semi della Felicità | `SEEDSOFHAPPINESSFIVE` |
| 255 | DQMJ3P | `くださいしアわせを` | しあわせのタネ ×5 | Semi della Felicità | `SEEDSOFHAPPINESSFIVE` |
| 255 | DQMJ3P | `シあワせノたネ` | しあわせのタネ ×5 | Semi della Felicità | `SEEDSOFHAPPINESSFIVE` |
| 260 | DQMJ3P | `しもふりにくほしいな` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 260 | DQMJ3P | `ほシいなしもふりにく` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 260 | DQMJ3P | `しもふりにくくださイ` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 260 | DQMJ3P | `くダさいしもふりにく` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 260 | DQMJ3P | `シもフりニく` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 235 | DQMJ3P | `しんじゅうせき10` | 神獣石 ×10 | Pietra di Incarnus | `INCARNUSSTONETEN` |
| 281 | DQMJ3P | `しあわせのたね100` | しあわせのタネ ×100 | Semi della Felicità | `SEEDSOFHAPPINEHUNDRED` |
| 282 | DQMJ3P | `しんじゅうせき20` | 神獣石 ×20 | Pietra di Incarnus | `INCARNUSSTONETWENTY` |
| 283 | DQMJ3P | `ちょうすきるのたね20` | 超スキルのタネ ×20 | Grandi Semi di Abilità | `LARGESKILLSEEDSTWENTY` |
| 326 | DQMJ3 | `A5OD9GVZCG` | ひかりの石 ×1 | Pietra del Sole | `SUNSTONE` |
| 327 | DQMJ3 | `AIHQ877TI9` | げんませき ×1 | Globo di Genma | `GENMASORB` |
| 328 | DQMJ3 | `AFEFBGNF9B` | マデュライト ×1 | Darkonium | `DARKONIUM` |
| 329 | DQMJ3 | `A1DE9P93TR` | ときのすいしょう ×1 | Cristallo Temporale | `TEMPORALCRYSTAL` |
| 330 | DQMJ3 | `AKZDN58BXE` | メタルのカケラ ×1 | Frammento Metallico | `METALFRAGMENT` |
| 331 | DQMJ3 | `AVI3OFS03A` | まじゅうの皮 ×1 | Pelle di Bestia Mannara | `WEREBEASTLEATHER` |
| 332 | DQMJ3 | `AC18KC0UJA` | ドラゴンの皮 ×1 | Pelle di Drago | `DRAGONLEATHER` |
| 333 | DQMJ3 | `AS9JJZ34C4` | かぜきりのはね ×1 | Ala Tagliente | `WINDCUTTINGWING` |
| 334 | DQMJ3 | `AM8ASATB0T` | 幻獣の皮 ×1 | Pelliccia di Bestia Mitica | `MYTHICALBEASTFUR` |
| 335 | DQMJ3 | `AEHES9V2NC` | ビッグサボテン ×1 | Grande Cactus | `BIGCACTUS` |
| 336 | DQMJ3 | `AL58BPW1CX` | まほうの樹木 ×1 | Rugiada Magica | `MAGICDEW` |
| 237 | DQMJ3 | `A6TVP4JB7L` | かがやきの樹液 ×1 | Linfa Lucente | `SHINYSAP` |
| 238 | DQMJ3 | `AV1GDUARXV` | ようせいの綿花 ×1 | Cotone degli Spiriti | `SPRITESCOTTON` |
| 239 | DQMJ3 | `AUKMYQY4HW` | あまつゆのいと ×1 | Filato di Goccia | `DROPLETYARN` |
| 240 | DQMJ3 | `AKRH853GV4` | よるのとばり ×1 | Tenda del Crepuscolo | `DUSKSCURTAIN` |
| 241 | DQMJ3 | `A2EYYOD4HF` | せいじゃのはい ×1 | Ceneri del Santo | `SAINTSASHES` |
| 242 | DQMJ3 | `AN1ZSOMATM` | 天使のソーマ ×1 | Soma Angelica | `ANGELSSOMA` |
| 243 | DQMJ3 | `ARC3FJ7J58` | 汗と涙の結晶 ×1 | Essenza del Lavoro | `ESSENCEOFLABOR` |
| 204 | DQMJ3 | `A5ULVBV5UC` | レッドオーブ ×1 | Sfera Rossa | `REDORB` |
| 205 | DQMJ3 | `AZP2W202ZC` | ブルーオーブ ×1 | Sfera Blu | `BLUEORB` |
| 206 | DQMJ3 | `A4AVDVI89Y` | イエローオーブ ×1 | Sfera Gialla | `YELLOWORB` |
| 207 | DQMJ3 | `ARHB4ZMVIB` | グリーンオーブ ×1 | Sfera Verde | `GREENORB` |
| 208 | DQMJ3 | `A6ETWNXDL7` | パープルオーブ ×1 | Sfera Viola | `PURPLEORB` |
| 249 | DQMJ3 | `AAJAJJG95T` | 元気玉 ×5 | Sfera di Luce | `BALLOFLIGHTFIVE` |
| 249 | DQMJ3 | `APR4I5W2HK` | 元気玉 ×5 | Sfera di Luce | `BALLOFLIGHTFIVE` |
| 210 | DQMJ3 | `ADAE04QYPL` | いのちのきのみ ×3 | Seme della Vita | `SEEDOFLIFE` |
| 210 | DQMJ3 | `A92I1XY8J3` | いのちのきのみ ×3 | Seme della Vita | `SEEDOFLIFE` |
| 211 | DQMJ3 | `AOOPFWGT61` | ふしぎなきのみ ×3 | Seme della Magia | `SEEDOFMAGIC` |
| 211 | DQMJ3 | `A29CV7ATUH` | ふしぎなきのみ ×3 | Seme della Magia | `SEEDOFMAGIC` |
| 212 | DQMJ3 | `ACWHU6GVTN` | ちからのタネ ×3 | Seme della Forza | `SEEDOFSTRENGTH` |
| 212 | DQMJ3 | `A5C8EJRSEK` | ちからのタネ ×3 | Seme della Forza | `SEEDOFSTRENGTH` |
| 213 | DQMJ3 | `AT5U8KF1WZ` | すばやさのタネ ×3 | Seme dell'Agilità | `SEEDOFAGILITY` |
| 213 | DQMJ3 | `AJ21PY9F9D` | すばやさのタネ ×3 | Seme dell'Agilità | `SEEDOFAGILITY` |
| 214 | DQMJ3 | `ARMFXSTXQC` | まもりのタネ ×3 | Seme della Resilienza | `SEEDOFRESILIENCE` |
| 214 | DQMJ3 | `ARBRZTVNVX` | まもりのタネ ×3 | Seme della Resilienza | `SEEDOFRESILIENCE` |
| 215 | DQMJ3 | `AAM439CHR5` | かしこさのタネ ×3 | Seme della Saggezza | `SEEDOFWISDOM` |
| 215 | DQMJ3 | `A687D3RC1C` | かしこさのタネ ×3 | Seme della Saggezza | `SEEDOFWISDOM` |
| 216 | DQMJ3 | `ACDUQN5PE9` | スキルのタネ ×3 | Semi di Abilità | `SKILLSEEDSTHREE` |
| 216 | DQMJ3 | `AO0QVAODYJ` | スキルのタネ ×3 | Semi di Abilità | `SKILLSEEDSTHREE` |
| 217 | DQMJ3 | `ASBG027Q52` | しあわせのタネ ×3 | Semi della Felicità | `SEEDSOFHAPPINESSTHREE` |
| 217 | DQMJ3 | `AGOKV0NZCL` | しあわせのタネ ×3 | Semi della Felicità | `SEEDSOFHAPPINESSTHREE` |
| 260 | DQMJ3 | `AEB23X9YC4` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 260 | DQMJ3 | `A2X153K9SG` | しもふりにく ×1 | Bocconi Bestiali | `BEASTIEBITES` |
| 219 | DQMJ3 | `A3JZONNQS9` | ばくだんいし ×1 | Frammento di Esplo-sasso | `ROCKBOMBSHARD` |
| 270 | DQMJ3 | `A8PV6YFGTR` | せかいじゅのしずく ×10 | Rugiada di Yggdrasil | `YGGDRASILDEW` |
| 271 | DQMJ3 | `AI6Z641616` | けんじゃのせいすい ×10 | Elisir di saggezza | `MAGISHOLYWATER` |
| 272 | DQMJ3 | `AE7OWJA8R9` | ふしぎなタンバリン ×3 | Tamburello della Tensione | `TIMBRELOFTENSION` |
| 273 | DQMJ3 | `AKTU23CDDC` | あやしいくすり ×3 | Medicina sbagliata | `MISTAKEMEDICINE` |
| 274 | DQMJ3 | `A6CSJKTN3W` | ちいさなメダル ×3 | Mini Medaglia | `MINIMEDALTHREE` |
| 274 | DQMJ3 | `AUMIVQ22XW` | ちいさなメダル ×3 | Mini Medaglia | `MINIMEDALTHREE` |
| 276 | DQMJ3 | `Bンドぼぢモニい` | 赤い宝石 ×1 | Gemma Rossa | `REDGEM` |
| 277 | DQMJ3 | `Bドっッケゥワッ` | 青い宝石 ×1 | Gemma Blu | `BLUEGEM` |
| 278 | DQMJ3 | `Bぜオヨニならハ` | 黄色の宝石 ×1 | Gemma Gialla | `YELLOWGEM` |
| 279 | DQMJ3 | `Bせやきれゆリト` | 緑の宝石 ×1 | Gemma Verde | `GREENGEM` |
| 380 | DQMJ3 | `Bぴぶたえでまヅ` | 小元気玉 ×3 | Piccola Sfera di Luce | `SMALLLIGHTBALL` |
| 380 | DQMJ3 | `Bゃウヤきてろプ` | 小元気玉 ×3 | Piccola Sfera di Luce | `SMALLLIGHTBALL` |
| 382 | DQMJ3 | `Bピグづッじはレ` | スキルのタネ ×1 | Semi di Abilità | `SKILLSEEDSONE` |
| 383 | DQMJ3 | `Bォゥポむニブぞ` | しあわせのタネ ×1 | Semi della Felicità | `SEEDSOFHAPPINESSONE` |
| 223 | DQMJ3 | `Bきてヨはもゆざ` | くんせいにく ×3 | Carne affumicata | `SMOKEDMEAT` |
| 285 | DQMJ3 | `Bドパふてぽもぽ` | 上やくそう ×10 | Medicina potente | `STRONGMEDICINETEN` |
| 286 | DQMJ3 | `Bヒモらぱゆドゼ` | アモールの水 ×3 | Essenza di Amor Seco | `AMORSECOESSENCE` |
| 287 | DQMJ3 | `Bダぶぎねラけブ` | まほうのせいすい ×10 | Acqua magica | `MAGICWATERTEN` |
| 288 | DQMJ3 | `Bほきポザれヅヌ` | ばんのうぐすり ×3 | Panacea | `PANACEATHREE` |
| 289 | DQMJ3 | `Bラぶポネフモに` | ちいさなメダル ×1 | Mini Medaglia | `MINIMEDALONE` |
| 289 | DQMJ3 | `Bイスこコツばつ` | ちいさなメダル ×1 | Mini Medaglia | `MINIMEDALONE` |
| 291 | DQMJ3 | `Cでゆあぞづ` | レッドアイ ×1 | Occhio Rosso | `REDEYE` |
| 292 | DQMJ3 | `Cヅオナダヅ` | ブルーアイ ×1 | Occhio Blu | `BLUEEYE` |
| 293 | DQMJ3 | `C鳥炎木士長` | イエローアイ ×1 | Occhio Giallo | `YELLOWEYE` |
| 294 | DQMJ3 | `CRPBPU` | グリーンアイ ×1 | Occhio Verde | `GREENEYE` |
| 295 | DQMJ3 | `Chkkri` | パープルアイ ×1 | Occhio Viola | `PURPLEEYE` |
| 296 | DQMJ3 | `C5/2↑～` | やくそう ×10 | Erba medicinale | `MEDICINALHERB` |
| 297 | DQMJ3 | `Cツりヲデキ` | どくけしそう ×5 | Erba per antidoti | `ANTIDOTALHERB` |
| 298 | DQMJ3 | `C曹闘ホぉ少` | 魔物のエサ ×3 | Mostrosnack | `MONSTERBAIT` |
| 218 | DQMJ3 | `Cりこせぬわ` | メタルストーン ×1 | Flipper | `PINBALL` |
| 300 | DQMJ3 | `Cじだめてつ` | いしころ ×99 | Ciottolo carino | `PRETTYPEBBLE` |

## 2. Dischi regalo della piazza Wi-Fi (Wi-Fi PRESENT -> プレゼントディスクの受け取り)

### Distribuzioni originali [G]
- Dal 2017-02-09, a casa: Slider Hero, Halcyon il Destriero (神馬アルシオン), dal 16/2 Dio (かみさま), dal 23/2 Chibi IV, dal 2/3 Chibi VIII.
- Solo in certi luoghi: Slider Girl (3DS Station), Tiko (7SPOT, 13/2-31/3), じげんりゅう (7SPOT, 1/3-31/3), Leo il Giovane (TSUTAYA, 16/2-30/4). Rugius, Vera e Kirlly via StreetPass in negozi ed eventi; Chibi I·II e III come codici di prenotazione.
- **Dal 1° maggio 2017** il menu dava, a casa, i dischi di Leo il Giovane, Tiko, じげんりゅう, Rugius, Vera, Kirlly, Chibi I·II, Chibi III, Gome-chan, Slime Premium, Omega Rolex e Aldarahla. **Un disco al giorno**; rispondendo "no" se ne proponeva un altro.
- Il plugin `Anthcny144/DQMJ3P-unobtainable-content` elenca 20 dischi scaricabili per DQMJ3P (id specie in `Sources/Content.cpp`).

### Logica del gioco [V codice]
- `FUN_00370e94`: task FGONLYT `BossPresentDisc.bin` (`re/notes/spotpass_boss.md`), poi `FUN_00370a70` legge il NsData (type5).
- `FUN_00439c20`: se la data salvata dell'ultimo ritiro e' oggi (`FUN_006bccf8`, anno/mese/giorno) -> `MenuMessagePresentDiscAlreadyReceived`. Il limite di un disco al giorno sta quindi nel salvataggio, non nel server.
- `FUN_0032be34` sceglie il regalo:
  - cerca il record A con il codice di 2 caratteri del luogo di connessione (dalle informazioni dell'access point). Se non c'e', usa `"00"` (casa) oppure `"DS"` (3DS Station): `DAT_0032c184` = `"00"`, `DAT_0032c188` = `"DS"`. Gli altri codici del campione di debug (`"TT"`, `"7N"`) corrispondono a TSUTAYA e 7SPOT [I];
  - in base al tipo del record (`u8` a +2):
    - 0 e >4: indice = giorni tra oggi e la data del record, modulo il numero di elementi (`FUN_00300f74`): un disco diverso ogni giorno;
    - 1: casuale (`FUN_00163868`);
    - 2: indice dal progresso del giocatore (prima voce di 47 flag di `0x7c77a0` presente nel profilo, `FUN_006b27a8`);
    - 3: come 2, ma con una probabilita' su due l'ultimo elemento;
    - 4: `FUN_0032b758`.
- L'elemento (16 B) e il mostro (record B da 0x48) hanno lo stesso formato del corpo dei pacchetti presente di tipo 0 (R001, R002, R036). `FUN_002eb7a4` valida specie e seed (`FUN_0012f254`) prima di mostrare `MenuMessagePresentDiscFoundNormalPresent` / `...SpecialPresent`.

### Stato
- Il server SpotPass serve il `BossPresentDisc.bin` originale (5780 B, caricato da Nintendo nel 2020). E' cifrato con la chiave BOSS delle console, che non abbiamo: non possiamo cambiarlo, ma il gioco ruota gia' da solo gli elementi del record `"00"`.
- Da fare: catturare una copia decifrata dall'extdata di Azahar durante un ritiro (il gioco la cancella subito dopo; `re/tools/capture_boss_nsdata.py`, poi `re/tools/bsdt.py decode` sul payload dopo l'header da 0x34 byte), elencare i record e capire quali dischi arrivano a casa. Il ritiro del 2026-11-02 era gia' fatto: si riprova il giorno dopo. I dischi dei soli negozi si potrebbero rendere disponibili con una patch di `FUN_0032be34` o con pacchetti presente di tipo 0 dal server SIL.
