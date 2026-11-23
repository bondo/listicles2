# Privatliv i Tally

Status: working draft 2026-11-21; not owner-approved (see issue #15)

> **Udkast, som ejeren skal godkende (opgave M1-O5, OQ-30).** Ikke godkendt, ikke juridisk rådgivning og ingen
> påstand om, at appen overholder nogen lov. Tekst i `[firkantede parenteser]` er pladsholdere, som ejeren udfylder.
> Den engelske tekst er `privacy-en.md`; de har de samme afsnit.

## 1. Hvem står bag

Tally er en lille app til fælles lister i husstanden, lavet af `[navn på den ansvarlige]`. Det er den person, der
bestemmer, hvilke data appen indsamler, og som har ansvaret for dem. Spørgsmål sendes til kontakten i afsnit 9.

## 2. Hvad Tally gemmer om dig

**Din konto** (Firebase Authentication, som Google driver):

- din e-mailadresse;
- din adgangskode, hvis du opretter dig med e-mail og adgangskode (kun Google gemmer den; den ligger aldrig i
  Tallys egen database);
- hvis du logger ind med Google: din Google-kontos id og de profiloplysninger, Google deler, når du logger ind:
  dit navn, din e-mailadresse og et link til dit profilbillede. Appen viser eller bruger ikke billedet.
  `[Tjekket på Firebase Auth-emulatoren (M1-67): login-posten gemmer dem alle. Skal tjekkes én gang med et rigtigt
  Google-login.]`
- hvis du slår totrinsbekræftelse til: det, der skal til for at tjekke koderne fra din godkendelsesapp;
- tekniske oplysninger, som Google logger, når du logger ind, fx din IP-adresse og hvilken slags enhed eller
  browser du bruger.

**Dine data i appen** (Cloud Firestore, som Google driver):

- det navn, du selv vælger ("Dit navn"). Din husstand ser navnet, men aldrig din e-mailadresse;
- din husstand: dens navn, medlemmernes navne og roller samt invitationslinks (hvert link indeholder husstandens
  navn), indtil de bliver brugt eller trukket tilbage, eller ryddet op, efter at de er udløbet (en invitation udløber
  efter 7 dage);
- dine lister og tingene på dem: navne, "Jeg har den", årstallene på samlelister, og hvem der tilføjede eller sidst
  ændrede en ting og hvornår.

**På din telefon:** en kopi af dine lister, så appen også virker uden net, og navnet på din husstand. Begge dele
slettes, når du logger ud eller sletter din konto. Telefonen husker også, hvornår du sidst åbnede hver liste på den,
så listerne kan sorteres; det forlader aldrig telefonen og slettes også, når du logger ud (når du logger ud, ryddes
alle Tallys data på telefonen for din konto).

Tally har ingen reklamer og **ingen analyseværktøjer**: appen måler ikke, hvordan du bruger den.

## 3. Hvem kan se dine data

- **Du** ser dine egne lister. En liste er privat, indtil du deler den med din husstand.
- **Din husstand** ser de lister, du deler med den, dit navn og om du er ejer. Den ser aldrig din e-mailadresse.
- **Google** driver tjenesterne ovenfor på vegne af Tally (som "databehandler"): Google gemmer og behandler
  e-mailadresser, adgangskoder og listedata, så appen kan fungere. Appen sender ikke dine data til andre tjenester.
- **Den, der hoster `tally.bjarkebjarke.dk`** (`[udbyder, når den er valgt]`): invitationslinks og siden til
  sletning (afsnit 7) er websider der. Når du åbner en af dem i en browser, ser udbyderen sidens adresse (for en
  invitation også invitationskoden) og din IP-adresse.
- **Den ansvarlige** (afsnit 1): hvis du skriver til kontakten (afsnit 9) eller beder om sletning uden appen
  (afsnit 7), får den ansvarlige din e-mailadresse og det, du skriver. `[Skal bekræftes, når siden til sletning er
  besluttet.]`

## 4. Hvor dine data ligger

- **Login (Firebase Authentication)** behandles **i USA**: Google driver kun tjenesten fra datacentre der.
- **Dine lister og din husstand (Cloud Firestore)** gemmes **i EU**, i Googles placering `eur3` (Belgien og
  Holland). Google kan behandle dem uden for EU efter egne vilkår.

## 5. Nedbrudsrapporter (kun hvis du slår dem til)

Nedbrudsrapporter er **slået fra**, indtil du slår "Send nedbrudsrapporter" til under Konto. Du kan altid slå dem
fra igen.

Når de er slået til, og appen går ned, sendes en rapport til Googles Firebase Crashlytics. Den viser fx, hvor i
appens kode det gik galt (nedbrudssporet), appens version, telefonmodel og Android-version, tekniske detaljer som
ledig hukommelse og lagerplads, og om telefonen er rootet, samt tilfældige id'er for installationen, så nedbrud fra
samme telefon kan samles. Appen sætter aldrig bruger-id eller egne nøgler i rapporten, så den indeholder hverken
navn, e-mailadresse eller indhold fra lister. Google gemmer nedbrudsrapporter i 90 dage.

## 6. Tjek af enheden (App Check)

For at beskytte dine data mod scripts og manipulerede enheder tjekker appen med Googles **Play Integrity**, at den
kører på en ægte Android-enhed. Selve appen bliver ikke tjekket. Ved hvert tjek sender appen oplysninger om
enhedens integritet til Google, og Google svarer med et token, der gælder i en begrænset periode, og som appen viser
til Firebase. Tally bruger kun resultatet til dette tjek.

## 7. Slet din konto

**I appen:** åbn **Konto**, og vælg **Slet konto**. Du bliver måske bedt om at logge ind igen først.

- Din konto, dit navn og alle de lister, du har oprettet (private og delte, med alle tingene på dem), bliver slettet.
  Medlemmerne af din husstand mister de lister, du har delt med dem.
- Er du ejer af en husstand med andre medlemmer, beder appen dig først om at overdrage ejerskabet. Intet bliver
  slettet, før det er sket.
- Er du det sidste medlem, bliver husstanden også slettet.
- Ting, du har tilføjet til andres lister, bliver på listerne, men dit navn fjernes fra dem.
  `[Skal bekræftes (M2, OQ-18): hvad der sker med sådanne ting, hvis du allerede havde forladt husstanden, før
  du slettede din konto.]`
- `[Skal bekræftes (M2, #205): en slettet husstand gemmes som en tom post, der stadig indeholder de tilfældige
  konto-id'er for den, der oprettede den, og ejeren, og et tilfældigt konto-id kan også blive stående på andres
  lister, som du sidst ændrede. Dit eget navn og din e-mailadresse gemmes ikke sammen med disse id'er.]`
- `[Skal bekræftes (M1, #281): invitationer, der er blevet tilbage under en slettet husstand, kan stadig indeholde
  dit tilfældige konto-id og husstandens navn.]`

**Uden appen:** du kan også bede om at få din konto slettet på en webside på `tally.bjarkebjarke.dk`
`[sidens adresse, når den er besluttet]`.

Google sletter de resterende login-oplysninger hos sig inden for 180 dage og loggede IP-adresser efter nogle uger.

## 8. Ændringer

Teksten kan blive ændret. Den gældende udgave er den, der står på denne side.

## 9. Dine rettigheder og kontakt

*Ikke juridisk rådgivning.* Du kan bede den ansvarlige om:

- **indsigt**: at se, hvad Tally har om dig;
- **rettelse**: at få rettet det, der er forkert (dit navn kan du selv ændre under Konto);
- **sletning**: i appen eller uden den (afsnit 7);
- og du kan **klage** til Datatilsynet.

Hvorfor Tally behandler dine data: for at levere den app, du har bedt om (en aftale), og for nedbrudsrapporter dit
samtykke (afbryderen "Send nedbrudsrapporter" under Konto, afsnit 5).

Spørgsmål om dine data eller denne tekst: `[kontakt]`.

_Udkast pr. `[dato]`._
