# Iepirkumu saraksta sadales optimizācija

Paša realizēts **Simulated Annealing (SA)** algoritms Python vidē. Katrai iepirkumu saraksta precei izvēlas vienu veikalu, minimizējot preču un piegādes kopējo summu. Gatavas optimizācijas algoritmu realizācijas netiek izmantotas; algoritms, pilnā pārlase, testu ģenerators un eksperimenti izmanto tikai Python standarta bibliotēku.

Darba apraksts: [report.docx](report.docx). Repozitorijs: [Niklavs-cmd/shopping-sa](https://github.com/Niklavs-cmd/shopping-sa).

## Ātra palaišana

Nepieciešams **Python 3.10 vai jaunāks**. Komandas izpilda projekta mapē. Nav obligātu ārējo pakotņu.

```console
python -m shopping_sa instances/small_06x03.json --seed 0 --exact
python -m shopping_sa instances/large_120x10.json --seed 7 --iterations 20000
python -m unittest discover -s tests -v
```

CLI izvada kopējās izmaksas, piegādes un preču summas pa veikaliem, izvēlēto veikalu katrai precei un izpildes laiku. `--json` dod mašīnlasāmu rezultātu. `--exact` papildus izpilda pilno pārlasi, ja atļauto sadalījumu skaits nepārsniedz 2 000 000; lieliem piemēriem šo opciju nelieto.

## Modelis

- Salīdzina vienu un to pašu preci dažādos veikalos. Visi dati ir **sintētiski un fiksēti**, bez aktuālu interneta cenu iegūšanas.
- Visu vienas preces nepieciešamo daudzumu pērk vienā veikalā. Nevar pirkt papildu preces sliekšņa sasniegšanai.
- Cenas ir **vienības cenas centos**; tās reizina ar `quantity`.
- `null` preces cenas vietā nozīmē nepieejamību. Katrā preces cenu masīvā ir pa elementam katram veikalam.
- Piegādi maksā vienreiz par izmantoto veikalu. Bezmaksas piegādes slieksni pārbauda pret veikala preču starpsummu, pirms piegādes pieskaitīšanas; vienādība ar slieksni dod bezmaksas piegādi.
- `free_delivery_threshold_cents: null` nozīmē, ka bezmaksas piegādes nav. Slieksnis 0 nozīmē bezmaksas piegādi visiem pasūtījumiem. Neizmantots veikals nekad neprasa piegādes maksu.
- Arī nulles cenas prece nozīmē, ka veikals ir izmantots; tādēļ izmantotību nenosaka tikai pēc starpsummas.

Minimāls ievades piemērs:

```json
{
  "name": "example",
  "stores": [
    {"name": "A", "delivery_cents": 500, "free_delivery_threshold_cents": 900},
    {"name": "B", "delivery_cents": 500, "free_delivery_threshold_cents": 900}
  ],
  "items": [
    {"name": "P001", "quantity": 1, "prices_cents": [400, 500]},
    {"name": "P002", "quantity": 1, "prices_cents": [500, 400]}
  ]
}
```

Atsevišķi lētāko preču izvēle maksā 18 EUR ar piegādi; abu preču pirkšana vienā veikalā maksā 9 EUR. Nepieciešamie daudzumi ir pozitīvi veseli skaitļi; naudas vērtības ir nenegatīvi veseli centi.

## SA realizācija

SA meklēšanas cikls, gājienu ģenerēšana, pieņemšanas nosacījums un dzesēšana ir uzrakstīti projektā `shopping_sa/solver.py`. Arī precīzā pilnā pārlase ir paša realizēta failā `shopping_sa/exact.py`. Standarta moduļi `random`, `math` un `time` nodrošina nejaušus skaitļus, matemātiskas funkcijas un laika mērīšanu; tie neizpilda optimizācijas algoritmu.

Sākuma sadalījumā katrai precei izvēlas lētāko pieejamo veikalu. Gājiens pārceļ vienu preci ar varbūtību 0,75 vai divas atšķirīgas preces ar varbūtību 0,25. Preces ar vienu pieejamu veikalu netiek pārvietotas. Izmaksu izmaiņas aprēķina tikai skartajiem veikaliem. Priekšlikumi ir simetriski; jebkurš atļauts sadalījums sasniedzams ar viena elementa gājieniem.

Ja `delta <= 0`, gājienu pieņem. Pretējā gadījumā to pieņem ar varbūtību `exp(-delta / temperature)`. Temperatūra centos ģeometriski samazinās no 2000 līdz 1: `T(k) = T0 * (Tend/T0)**(k/(K-1))`. Kodā izmantota matemātiski ekvivalenta logaritmu interpolācija. `K=1` izmanto sākuma temperatūru; `K=0` atgriež sākuma risinājumu. Ja nevienu preci nevar pārvietot, atgriež sākuma risinājumu ar 0 izpildītām iterācijām.

Saglabā labāko redzēto risinājumu, ieskaitot sākuma sadalījumu. Viena palaidiena rezultāts tādēļ nav dārgāks par sākuma risinājumu, taču SA globālu optimumu negarantē. Vienāda ievade, parametri, sēkla un Python nejaušo skaitļu realizācija atkārto sadalījumu un izmaksas; laiks var mainīties.

## Testi un eksperiments

Ir 30 `unittest` testi: piegādes robežgadījumi, neizmantojams/neizmantots veikals, daudzumi, nulles cena, nederīga ievade, neatkarīga mazu piemēru pilnā pārlase, SA rezultāta atļautība, summu atbilstība, reproducējamība un saglabātā labākā risinājuma garantija. Ģeneratora testi pārbauda arī visu JSON failu precīzu reproducējamību.

```console
python -m unittest discover -s tests -v
python scripts/generate_instances.py
python scripts/benchmark.py --output-dir work/recheck
```

Pēdējā komanda atkārto pilnu eksperimentu atsevišķā mapē, saglabājot iesniegtos mērījumus. `python scripts/benchmark.py` pārraksta `results/` rezultātus. Īsai darbības pārbaudei:

```console
python scripts/benchmark.py --runs 2 --iterations 1000 --reference-runs 2 --reference-iterations 2000 --output-dir work/smoke
```

Pilnajā eksperimentā katram no 8 piemēriem ir 20 palaidieni ar sēklām 0–19 un 20 000 iterāciju. Četriem mazajiem piemēriem precīzo optimumu nosaka paša realizēta pilnā pārlase. Lielajiem etalons ir minimums no bāzes, 20 pamata un 10 papildu palaidieniem (sēklas 1000–1009, katram 100 000 iterāciju). Papildu palaidienos pamīšus izmanto lētāko un nejaušu atļautu sākuma sadalījumu.

Lielo piemēru etaloni ir **labākie šajā eksperimentā atrastie risinājumi**, nevis pierādīti optimumi. Ja etalons sakristu ar visu lētāko preču summu bez piegādes, optimalitāti pierādītu šī zemākā robeža; iesniegtajā eksperimentā lielajiem piemēriem tā nenotika.

| Preces × veikali | Etalons EUR | Etalona veids | SA labākais EUR | SA vidējais EUR | Vidējā novirze % | Etalona trāpījumi |
|---|---:|---|---:|---:|---:|---:|
| 6 × 3 | 36,87 | Precīzs optimums | 36,87 | 36,8700 | 0,0000 | 20/20 |
| 8 × 4 | 67,12 | Precīzs optimums | 67,12 | 67,1200 | 0,0000 | 20/20 |
| 10 × 4 | 75,56 | Precīzs optimums | 75,56 | 75,5825 | 0,0298 | 19/20 |
| 12 × 3 | 132,19 | Precīzs optimums | 132,19 | 132,1910 | 0,0008 | 19/20 |
| 20 × 5 | 221,09 | Labākais atrastais | 221,09 | 221,2070 | 0,0529 | 15/20 |
| 40 × 6 | 359,02 | Labākais atrastais | 359,02 | 359,7975 | 0,2166 | 2/20 |
| 80 × 8 | 631,53 | Labākais atrastais | 631,53 | 636,3655 | 0,7657 | 1/20 |
| 120 × 10 | 908,16 | Labākais atrastais | 909,08 | 910,6775 | 0,2772 | 0/20 |

Novirze: `100 * (SA_izmaksas - etalons) / etalons`. Vidējās vērtības aprēķina no visu 20 palaidienu labākajām summām. Nulles etalonam nulles izmaksu novirze definēta kā 0; pozitīvām izmaksām tā nav galīga.

Mērījumi: CPython 3.13.2, Windows 11, Intel64 Family 6 Model 170 Stepping 4, 14 loģiskie procesori. Vidējais SA laiks atkarībā no piemēra bija aptuveni 0,117–0,213 s. `time.perf_counter` mērījums ietver SA inicializāciju un meklēšanu, bet ne failu lasīšanu, pilno pārlasi vai etalona veidošanu. Veikta viena secīga eksperimentu sērija bez procesora piesaistes un operētājsistēmas fona noslodzes kontroles.

Mazajos piemēros optimums sasniegts 78/80 palaidienos. Šajā mērījumā pilnā pārlase mazajiem piemēriem bija ātrāka nekā vidējais SA palaidiens. Lielākajam piemēram nevienā pamata palaidienā nav sasniegts papildu meklēšanas atrastais etalons. Viens sintētisks piemērs katram izmēram nav pietiekams vispārīgam mērogošanās apgalvojumam; nulles novirze pret labāko atrasto lielajā piemērā nepierāda optimumu.

## Failu struktūra

| Fails vai mape | Saturs |
|---|---|
| `shopping_sa/model.py` | Ievades pārbaude, izmaksu aprēķins, JSON ielāde |
| `shopping_sa/solver.py` | Paša realizēts SA |
| `shopping_sa/exact.py` | Neatkarīga pilnā pārlase |
| `shopping_sa/__main__.py` | Komandrindas saskarne |
| `instances/` | Astoņi pamata piemēri un divi robežgadījumi apakšmapē |
| `scripts/generate_instances.py` | Deterministisks datu ģenerators |
| `scripts/benchmark.py` | Eksperimentu atkārtošana un CSV/JSON rezultāti |
| `tests/` | Vienību un neatkarīgas pareizības pārbaudes |
| `results/runs.csv` | Visi 160 pamata palaidieni |
| `results/reference_runs.csv` | Visi 40 garie papildu palaidieni |
| `results/summary.csv` | Izmaksu, noviržu un laika kopsavilkums |
| `results/solutions.json` | Visu palaidienu sadalījumi un precīzie risinājumi |
| `results/metadata.json` | Parametri, vide un datu/koda SHA256 kontrolsummas |

## Avots

Kirkpatrick S., Gelatt C. D., Vecchi M. P. (1983). *Optimization by Simulated Annealing*. Science 220(4598), 671–680. [DOI: 10.1126/science.220.4598.671](https://doi.org/10.1126/science.220.4598.671).
