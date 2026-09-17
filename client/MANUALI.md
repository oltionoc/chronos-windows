# Chronos — Manuali i Përdorimit

Ky manual shpjegon si përdoret Chronos, sistemi që mban orarin e punës dhe
përgatit pagat. Është shkruar për njerëz që nuk merren me kompjutera dhe nuk
kërkon njohuri teknike.

Lexojeni një herë nga fillimi. Pastaj përdorni pjesën që ju duhet.

---

## Përmbajtja

1. [Çka bën ky sistem](#1-çka-bën-ky-sistem)
2. [Si hyni në sistem](#2-si-hyni-në-sistem)
3. [Faqja kryesore (Paneli)](#3-faqja-kryesore-paneli)
4. [Njoftimet](#4-njoftimet)
5. [Punonjësit](#5-punonjësit)
6. [Orari i punës (turnet)](#6-orari-i-punës-turnet)
7. [Caktimi i turnit te punonjësi](#7-caktimi-i-turnit-te-punonjësi)
8. [Pajisjet (aparati i shenjimit)](#8-pajisjet-aparati-i-shenjimit)
9. [Prezenca ditore](#9-prezenca-ditore)
10. [Shenjimet (të dhënat e papërpunuara)](#10-shenjimet-të-dhënat-e-papërpunuara)
11. [Lejet](#11-lejet)
12. [Festat zyrtare](#12-festat-zyrtare)
13. [Rregullat e pagës](#13-rregullat-e-pagës)
14. [Paga mujore](#14-paga-mujore)
15. [Përdoruesit e sistemit](#15-përdoruesit-e-sistemit)
16. [Çka të bëni kur...](#16-çka-të-bëni-kur)
17. [Kopjet rezervë](#17-kopjet-rezervë)
18. [Fjalorth](#18-fjalorth)

---

## 1. Çka bën ky sistem

Punonjësi shenjon me gisht ose me kartelë në aparat kur vjen dhe kur shkon.
Aparati i dërgon ato shenjime te Chronos. Sistemi pastaj:

- llogarit kush ka ardhur me vonesë dhe sa minuta,
- llogarit orët shtesë,
- shënon kush ka munguar dhe kush ka qenë me leje,
- në fund të muajit përgatit pagën me zbritjet dhe shtesat.

Ju nuk shkruani asgjë me dorë për prezencën. Ju vetëm kontrolloni dhe
konfirmoni.

**Dy role në sistem:**

| Roli | Çka sheh |
|------|----------|
| **Administrator** | Të gjitha lokacionet dhe të gjitha të dhënat. |
| **Menaxher** | Vetëm lokacionin e vet, por atje ka qasje të plotë. |

---

## 2. Si hyni në sistem

1. Hapni shfletuesin (Chrome, Edge) në kompjuter.
2. Shkruani adresën që ju është dhënë, për shembull `http://192.168.1.50:8080`.
3. Shkruani emrin e përdoruesit dhe fjalëkalimin.

**Herën e parë** sistemi ju detyron ta ndërroni fjalëkalimin. Kjo është e
qëllimshme. Zgjidhni një fjalëkalim që nuk e përdorni gjetiu dhe mos ia jepni
askujt. Çdo veprim në sistem regjistrohet nën emrin tuaj.

Lart djathtas mund të ndërroni gjuhën: **SQ** (shqip) ose **EN** (anglisht).

---

## 3. Faqja kryesore (Paneli)

Kur hyni, shihni kartela me numrat e ditës së sotme:

- **Prezentë** — sa punonjës kanë ardhur sot. Brenda së njëjtës kartelë
  shkruan edhe **sa janë aktualisht në objekt** (dikush që ka shenjuar daljen
  nuk numërohet më).
- **Me vonesë** — sa kanë ardhur pas orarit, duke llogaritur edhe minutat e
  tolerancës.
- **Me leje** — kush është me leje sot dhe për çfarë arsye.
- **Në pushim** — kush ka shenjuar daljen për pushim dhe nuk është kthyer ende.
- **Mungesa** — kush ishte i planifikuar të punojë sot dhe nuk ka shenjuar.

Poshtë kartelave keni grafikun e javës dhe listën e njoftimeve më të fundit.

---

## 4. Njoftimet

Menyja **Njoftimet** është vendi më i rëndësishëm i sistemit. Aty dalin
problemet që sistemi i gjen vetë. **Hapeni çdo ditë.**

| Njoftimi | Çka do të thotë | Çka të bëni |
|----------|-----------------|-------------|
| Nuk ka dalje të regjistruar | Punonjësi ka shenjuar hyrjen, jo daljen | Pyeteni kur ka dalë, korrigjoni ose lëreni si është |
| Filloi pushimin, nuk u kthye | Ka shenjuar daljen për pushim dhe s'është kthyer | Kontrolloni atë ditë |
| Nuk ka shenjuar sot | Ishte i planifikuar, s'ka ardhur, nuk është me leje | Telefonojini; nëse është me leje, shtojeni lejen |
| Shenjim jashtë orarit | Ka shenjuar në një ditë ose orë kur nuk punon | Shikoni a ka ndërruar turn me dikë, ose a është gabim |
| Orë shtesë në pritje aprovimi | Ka orë shtesë që nuk paguhen pa aprovim | Shkoni te Prezenca ditore dhe aprovojini nëse janë të vërteta |
| Shenjime të pazgjidhura | Aparati dërgoi shenjim nga një ID që nuk njihet | Dikush nuk është regjistruar si duhet te pajisja |
| Pajisja nuk është sinkronizuar 24 orë | Aparati është fikur ose ka humbur rrjetin | Kontrolloni rrymën dhe kabllin e rrjetit |
| **Ora e pajisjes është gabim** | Ora e aparatit nuk përputhet me serverin | **Urgjente.** Rregulloni orën e aparatit, pastaj rillogarisni ato ditë |
| Kopja rezervë dështoi / mungon | Të dhënat nuk po ruhen | Njoftoni menjëherë personin që e mirëmban sistemin |

> **Pse ora e pajisjes është urgjente:** çdo shenjim e merr orën nga aparati,
> jo nga kompjuteri. Nëse ora e aparatit është gabim një orë, atëherë të
> gjithë punonjësit dalin një orë me vonesë, dhe kjo shkon direkt në pagë.

---

## 5. Punonjësit

**Për të shtuar një punonjës:** Punonjësit → **Punonjës i Ri**.

Fushat që duhen:

- **Kodi i punonjësit** — numri juaj i brendshëm, p.sh. `P-001`. Duhet të jetë
  unik.
- **Emri dhe mbiemri**.
- **Lokacioni** — ku punon.
- **Data e fillimit të punës**.
- **Paga bazë (€)** — paga mujore bruto mbi të cilën llogariten zbritjet dhe
  shtesat.

Pastaj hapni punonjësin dhe plotësoni dy gjëra të rëndësishme:

**a) Regjistrimet në pajisje** — lidhja mes njeriut dhe aparatit. Te aparati
çdo person ka një numër (ID). Ai numër shkruhet këtu. Pa këtë, shenjimet e tij
vijnë por sistemi nuk di se kujt i takojnë.

**b) Caktimet e turnit** — cili orar i takon. Shih kapitullin 7.

> Punonjësit nuk fshihen. Nëse dikush largohet nga puna, ndryshoni
> **Statusin** në `I larguar`. Kështu historiku dhe pagat e vjetra mbeten të
> sakta.

---

## 6. Orari i punës (turnet)

Orari përcakton se kur pritet të punojë dikush. Krijohet një herë dhe u
caktohet shumë punonjësve.

**Orari i Punës → Orar i Ri.**

- **Emri** — p.sh. `Turni i mëngjesit`.
- **Lokacioni**.
- **Minutat e tolerancës** — sa minuta vonesë falen. Nëse vendosni `5` dhe
  orari fillon 08:00, dikush që shenjon 08:04 nuk është me vonesë; 08:10 është
  me vonesë 10 minuta (numërohen nga 08:00, jo nga 08:05).

Pastaj për çdo ditë të javës:

- **Ndizeni ose fikeni ditën** — e fikur do të thotë ditë pushimi.
- **Orari i punës** — p.sh. 08:00 – 16:00.
- **Shto bllok pune** — për turne të ndara. Shembull: 08:00 – 12:00 dhe pastaj
  17:00 – 21:00. Koha në mes nuk numërohet as si punë, as si dalje e parakohshme.
- **Shto pushim** — dritarja e pushimit, p.sh. 12:00 – 12:30. Shenjimet brenda
  kësaj kohe njihen si pushim, jo si dalje nga puna.

---

## 7. Caktimi i turnit te punonjësi

Hapni punonjësin → skeda **Caktimet e Turnit** → **Cakto Turn**.

- **Në fuqi nga** — data prej së cilës vlen ky orar.
- **Në fuqi deri** — lëreni bosh nëse vazhdon.

**Një punonjës mund të ketë disa turne njëkohësisht**, me kusht që të punojnë
ditë të ndryshme të javës. Shembull:

| Orari | Ditët | Koha |
|-------|-------|------|
| Turni i kafes | E hënë, e martë | 08:00 – 16:00 |
| Turni i zyrës | E mërkurë, e enjte, e premte | 09:00 – 17:00 |

Të dyja rrinë aktive në të njëjtën kohë. Sistemi e di vetë se e hëna i takon
të parit.

Nëse provoni të shtoni dy orare që mbulojnë **të njëjtën ditë**, sistemi e
refuzon. Kjo është me qëllim: askush nuk do të mund të thoshte se cili orar
vlen atë ditë.

Për të ndryshuar ose hequr një caktim, përdorni **Ndrysho** ose **Fshij** në
rreshtin përkatës.

---

## 8. Pajisjet (aparati i shenjimit)

**Pajisjet** → hapni një pajisje. Aty keni dy butona:

- **Testo Lidhjen** — kontrollon nëse aparati përgjigjet. Në të njëjtën kohë e
  lexon edhe **orën e aparatit** dhe ju thotë nëse është gabim.
- **Sinkronizo Tani** — merr menjëherë shenjimet e reja, pa pritur ciklin
  automatik.

Në të njëjtën faqe shihni:

- **Sinkronizimi i fundit** — kur janë marrë shenjimet e fundit.
- **Ora e Pajisjes** — nëse shkruan `E sinkronizuar me serverin`, gjithçka
  është në rregull. Nëse shkruan që është gabim me X minuta, rregullojeni
  orën e aparatit dhe pastaj shtypni përsëri **Testo Lidhjen**.

Normalisht sistemi i merr shenjimet vetë çdo pak minuta. Këta butona janë për
kur jeni duke instaluar ose duke kontrolluar diçka.

---

## 9. Prezenca ditore

**Prezenca → Statusi Ditor.** Kjo është tabela kryesore e kontrollit. Një
rresht për çdo punonjës për çdo ditë.

Kolonat:

- **Orari** — çka ishte planifikuar.
- **Hyrja / Dalja** — çka ka ndodhur realisht.
- **Vonesa** — minutat e vonesës pas tolerancës.
- **Dalje e parakohshme** — minutat para mbarimit të orarit.
- **Orë shtesë** — minutat mbi orarin.
- **Pushimi** — minutat e pushimit.
- **Statusi** — shih tabelën më poshtë.

| Statusi | Domethënia |
|---------|------------|
| Prezent | Ka punuar normalisht |
| Me vonesë | Ka ardhur pas tolerancës |
| Mungesë | Ishte i planifikuar, nuk ka shenjuar |
| Me leje | Ka leje të regjistruar atë ditë |
| Festë | Festë zyrtare |
| Pa orar | Nuk ishte i planifikuar të punojë |

**Arsyetimi i mungesës:** te kolona e fundit mund ta shënoni një mungesë si
`E arsyeshme`. Mungesa e arsyeshme nuk zbritet nga paga.

**Aprovimi i orëve shtesë:** nëse te rregullat keni kërkuar aprovim, orët
shtesë shfaqen si `Në pritje aprovimi`. Shtypni **Aprovo** për t'i paguar.
Nëse nuk aprovohen, minutat mbesin të regjistruara por nuk paguhen.

> Nëse aprovoni një ditë dhe më vonë vjen edhe një shenjim që e ndryshon
> numrin e minutave, aprovimi anulohet vetë. Kështu nuk paguhet kurrë një
> shifër që askush nuk e ka parë.

**Rillogaritja:** butoni **Rillogarit** e detyron sistemin t'i llogarisë
sërish ditët e zgjedhura. Përdoreni pasi të keni ndryshuar një orar, të keni
shtuar një festë, ose të keni rregulluar orën e aparatit.

---

## 10. Shenjimet (të dhënat e papërpunuara)

**Prezenca → Shenjimet.** Këtu janë shenjimet ashtu siç kanë ardhur nga
aparati, pa përpunim. Përdoreni kur dikush thotë "unë kam shenjuar" dhe doni
ta shihni të vërtetën.

Llojet e shenjimeve:

| Lloji | Kur ndodh |
|-------|-----------|
| Hyrje | Fillimi i punës |
| Dalje | Mbarimi i punës |
| Dalje pushimi | Del për pushim |
| Hyrje pushimi | Kthehet nga pushimi |
| Fillim orësh shtesë | Fillon orët shtesë (butoni në aparat) |
| Mbarim orësh shtesë | Mbaron orët shtesë |
| E paklasifikuar | Sistemi s'e ka lidhur dot me asnjë punonjës |

Nëse një shenjim është **i paklasifikuar**, do të thotë se numri i përdorur te
aparati nuk i takon askujt në sistem. Zgjidheni duke ia caktuar punonjësit të
duhur, pastaj shtoni regjistrimin te pajisja që të mos përsëritet.

---

## 11. Lejet

**Lejet → Leje e Re.** Zgjidhni punonjësin, llojin e lejes dhe datat.

Llojet e lejeve vijnë të gatshme (pushim vjetor, leje mjekësore, çështje
private, punë zyrtare) dhe mund të shtoni të tjera te Konfigurimi.

**Lejet nuk kanë proces aprovimi.** Kur shtoni një leje, sistemi thjesht e di
se ai person nuk pritet të shenjojë ato ditë. Nuk shënohet mungesë dhe nuk
bëhet zbritje.

Te llojet e lejeve përcaktohet nëse leja është **e paguar** apo jo. Kjo ndikon
në pagë: ditët e papaguara dalin veçmas te fleta e pagës.

---

## 12. Festat zyrtare

**Konfigurimi → Festat Zyrtare.**

Kjo listë duhet plotësuar, përndryshe çdo festë zyrtare do të llogaritet si
**mungesë e paarsyeshme** dhe do t'u zbritet punonjësve nga paga.

Për çdo festë shkruani:

- **Datën**.
- **Emrin** në shqip dhe anglisht.
- **Lokacionin** — lëreni bosh që të vlejë për të gjitha lokacionet.
- **Përsëritet çdo vit** — ndizeni për festat me datë fikse (p.sh. 1 Janari).
  Për festat që ndryshojnë datë çdo vit (Bajrami, Pashkët), lëreni të fikur
  dhe shtoni datën e saktë për çdo vit.

Çka ndodh në një ditë feste:

- Kush nuk punon: statusi `Festë`, pa mungesë, pa zbritje.
- Kush punon: orët e tij paguhen me tarifën e festës, nëse ajo është caktuar
  te rregullat e orëve shtesë.
- Nëse dikush ishte me leje atë ditë, festa nuk ia han ditën e lejes.

> Datat e festave zyrtare i vendosni ju sipas ligjit dhe vendimit të firmës.
> Sistemi nuk vjen me lista të gatshme, sepse ato ndryshojnë dhe përgjegjësia
> është e juaja.

---

## 13. Rregullat e pagës

Te **Konfigurimi** përcaktohet politika. Çdo rregull ka datë prej së cilës
vlen, kështu që një ndryshim sot nuk i prek muajt e kaluar.

### Penalitetet (vonesat)

Dy mënyra:

- **Fiks për minutë** — p.sh. 0.10 € për çdo minutë vonesë. 20 minuta = 2.00 €.
- **Tolerancë me shumë fikse** — p.sh. deri në 10 minuta falet; mbi 10 minuta
  zbritet një shumë fikse, p.sh. 5.00 €. Njësoj për 11 minuta dhe për 40.

Mund të vendosni edhe **zbritje maksimale ditore**, që askush të mos humbasë
më shumë se aq në një ditë, dhe një tarifë të veçantë për **dalje të
parakohshme**.

### Orët shtesë

- **Tarifa për orë** — sa paguhet ora shtesë.
- **Pragu ditor** — sa minuta mbi orar nuk numërohen. P.sh. me prag 30, dikush
  që rri 20 minuta më gjatë nuk fiton asgjë; kush rri 50 minuta fiton 20.
- **Tarifa e fundjavës** dhe **tarifa e festave** — nëse janë të ndryshme.
- **Kërkon aprovim** — nëse ndizet, orët shtesë nuk paguhen pa aprovimin tuaj.
- **Kufiri mujor** — maksimumi i orëve shtesë që paguhen në muaj.

> **E rëndësishme:** pragu ditor vlen vetëm kur dikush thjesht rri më gjatë.
> Nëse punonjësi shtyp **Fillim orësh shtesë** në aparat, ato minuta paguhen
> të plota, pa prag. Arsyeja: pragu është aty për t'i injoruar 10 minutat që
> dikush vonohet duke dalë, jo për t'i shkurtuar orët shtesë të vendosura me
> qëllim.

### Rregulli i mungesave

Sa zbritet për një ditë mungese të paarsyeshme:

- **Shumë fikse** — p.sh. 20.00 € për ditë.
- **Pjesë e pagës ditore** — p.sh. `1.0` do të thotë një ditë e plotë pune
  (paga bazë pjesëtuar me ditët e muajit).

---

## 14. Paga mujore

**Paga → Llogaritje e Re.** Zgjidhni muajin dhe lokacionin.

Sistemi krijon një listë me nga një rresht për çdo punonjës:

```
Paga bazë
 − zbritjet për vonesa dhe dalje të parakohshme
 − zbritjet për mungesa
 + shtesa për orët shtesë
 ± korrigjimet manuale
 = Paga neto
```

**Përpara se ta mbyllni llogaritjen:**

1. Hapni **Njoftimet** dhe rregulloni çka mundeni (dalje që mungojnë, shenjime
   të pazgjidhura, orë shtesë në pritje).
2. Kontrolloni te Prezenca Ditore mungesat e muajit dhe arsyetoni ato që janë
   të arsyeshme.
3. Nëse keni ndryshuar diçka, shtypni **Rillogarit** për ato datat.

**Korrigjimet manuale:** te çdo rresht mund të shtoni një **bonus** ose një
**zbritje** me arsye të shkruar. Kjo është për gjërat që sistemi nuk i di.

**Mbyllja (finalizimi):** kur shtypni **Finalizo**, llogaritja bllokohet dhe
nuk ndryshohet më. Vetëm pas kësaj mund të shkarkoni fletët e pagës. Nëse
gjeni gabim pas mbylljes, llogaritja e mbyllur mbetet si dëshmi dhe
korrigjimi bëhet në muajin pasues.

**Shkarkimi:** butoni i eksportit ju jep dosje Excel, ose të gjithë listën, ose
fletë page për një punonjës.

---

## 15. Përdoruesit e sistemit

**Cilësimet → Llogaritë e Përdoruesve** (vetëm administratori).

Kur krijoni një përdorues, i jepni një fjalëkalim fillestar. Sistemi e detyron
atë person ta ndërrojë herën e parë.

Për një **menaxher** duhet caktuar **lokacioni**. Menaxheri pa lokacion nuk
sheh asgjë — dhe kjo është me qëllim, që askush të mos shohë të dhëna pa i
takuar. Sistemi ju njofton nëse harroni.

---

## 16. Çka të bëni kur...

**...dikush ka harruar të shenjojë daljen.**
Njoftimi "Nuk ka dalje të regjistruar" e tregon. Sistemi nuk ia zbret pagën
për këtë. Pyeteni personin dhe, nëse duhet, shtoni një korrigjim manual te
paga e muajit.

**...dikush del me vonesë por nuk ka qenë.**
Kontrolloni te **Pajisjet** orën e aparatit. Nëse ora është gabim, rregullojeni
dhe pastaj shtypni **Rillogarit** për ato ditë. Kontrolloni edhe orarin që i
është caktuar — mos i është caktuar turni i gabuar.

**...dikush ka ndërruar turn me një kolegë.**
Shtoni një caktim turni për atë periudhë, ose arsyetoni mungesën dhe shtoni
korrigjim manual te paga.

**...aparati është fikur një ditë.**
Shenjimet rrinë të ruajtura në vetë aparatin. Kur ndizet përsëri, sistemi i
merr vetë. Nëse kanë kaluar shumë ditë, shtypni **Sinkronizo Tani**.

**...ka ikur rryma.**
Kur kthehet rryma, kompjuteri dhe programi ndizen vetë. Aparati i ruan
shenjimet ndërkohë. Kontrolloni te Pajisjet që sinkronizimi i fundit të jetë i
freskët.

**...një punonjës i ri fillon punën.**
1. Shtojeni te Punonjësit. 2. Regjistrojeni në aparat dhe shënoni ID-në e tij
te Regjistrimet në Pajisje. 3. Caktojini turnin.

---

## 17. Kopjet rezervë

Sistemi bën vetë një kopje të bazës së të dhënave çdo natë dhe e ruan në
kompjuter, në dosjen `backups`.

Dy gjëra janë përgjegjësi e njeriut:

1. **Kopjoni atë dosje diku tjetër** — në një disk të jashtëm, në një dosje
   rrjeti, ose në internet. Nëse prishet disku i kompjuterit, kopjet që janë
   në të njëjtin disk humbin bashkë me të.
2. **Shikoni njoftimet.** Nëse del njoftimi që kopja rezervë dështoi ose
   mungon, njoftoni menjëherë personin që e mirëmban sistemin. Mos e lini për
   më vonë.

---

## 18. Fjalorth

| Fjala | Shpjegimi |
|-------|-----------|
| **Shenjim** | Një prekje e gishtit ose kartelës te aparati |
| **Turni / orari** | Kur pritet të punojë dikush |
| **Toleranca** | Minutat e vonesës që falen |
| **Bllok pune** | Një pjesë e ditës së punës; një ditë mund të ketë dy |
| **Orë shtesë** | Koha e punuar mbi orarin |
| **Pragu** | Minutat mbi orar që nuk numërohen si orë shtesë |
| **Mungesë e arsyeshme** | Mungesë që nuk zbritet nga paga |
| **Rillogaritje** | Detyrimi i sistemit të llogarisë sërish ditët e zgjedhura |
| **Finalizim** | Mbyllja përfundimtare e pagës së muajit |
| **Sinkronizim** | Marrja e shenjimeve nga aparati |

---

*Nëse diçka nuk përputhet me atë që shkruan ky manual, mos e ndryshoni pagën
me dorë pa e kuptuar shkakun. Njoftoni personin që e mirëmban sistemin.*
