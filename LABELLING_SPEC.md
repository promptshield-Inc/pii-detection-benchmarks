# Labelling spec (PII-detection benchmark)

This is the brief the corpus in `corpus/` was written from, kept verbatim
except for paths that only exist in promptShield's own repository. For the
2026-10-21 revision each language was written by a separate AI agent working
from this spec, with documents 1 to 6 below (document 7 was skipped) and
targets of at least 100 sensitive spans, 45 of them names, and 50 trap words
per language.

You are writing realistic business documents, natively, in ONE language, with
every piece of personal data labelled inline. The documents are rendered to
PDF and fed to an anonymizer; your labels are the answer key it is scored
against, word by word. Label accuracy matters more than anything else.

`<corpus>` below is the corpus directory you were given.

## Hard rules
- Write ONLY inside `<corpus>/<lang>/` (the file `docs.json`, plus the `pdf/`
  folder the verifier creates). Do not touch anything else anywhere.
- Do NOT read the anonymizer's source code, its demo documents, its earlier
  test corpora or any other language's corpus. The corpus must be independent
  of the engine: never tune a sentence to make detection easier or harder than
  real life.
- Do not reuse names, companies or numbers from any other corpus.
- All people, companies, numbers are fictional but must LOOK real (valid-looking
  formats, plausible check digits where cheap; real city/street naming style).
- Write natively (not a translation of English): local document conventions,
  local legal/administrative vocabulary, local name distribution.

## File format: `<corpus>/<lang>/docs.json`
A JSON array of documents:
```json
{"id": "fr01_contrat", "lang": "fr", "country": ["FR"], "kind": "contract",
 "title": "…", "dense": false,
 "pages": [ [ block, block, … ], [ …page 2… ] ] }
```
Optional field `"formats"` (alias `"format"`): a list drawn from `pdf docx txt scan xlsx pptx`.
Every document is scored as a born-digital PDF, a Word file, a plain-text file
and a 300-dpi scan whatever this says; the field only opts a document INTO the
spreadsheet (`xlsx`) and slide-deck (`pptx`) renderings, overriding the
default (xlsx = the invoice and the bank statement, docs 02 and 03; pptx =
docs 02 and 05). Use it for a document that genuinely lives in that format in
real life (a spreadsheet-exported ledger, a short deck); leave it out
otherwise. Write the document the same way whatever you list: the labels are
the same answer key in every format.

Block kinds:
- `{"t":"h","text":"…"}` heading (bold)
- `{"t":"p","text":"…"}` wrapped paragraph (optional `"size": 9`)
- `{"t":"lines","text":"line1\nline2\n…"}` one visual line per `\n` (letterheads,
  address blocks, email headers, signature lines, witness lists)
- `{"t":"table","rows":[["h1","h2"],["c1","c2"]],"widths":[1,3,1],"size":8}`
  first row = header. Cells may contain markup.
- `{"t":"cols","left":"l1\nl2","right":"l1\nl2"}` two side-by-side columns of
  lines (typical signature block: party A left, party B right)
- `{"t":"space","h":12}`

## Inline labels: `[[TAG|surface text]]`
Surface text is copied verbatim into the document. No nesting. A span may
contain `\n` (e.g. a name forced across two lines).

MUST be redacted (a miss is a leak):
- `PER`   a person's name exactly as written: given names, surnames, particles
          (van der, de la, da, dos, von, di, del), hyphens, initials
          ("J.-P. Martin", "M. A. Rossi"). Surname-first forms ("DUPONT Jean",
          "Rossi Mario") are one PER span. Do NOT include honorifics/titles.
- `ORG`   private organisation that identifies a party: client/employer/
          counterparty/supplier companies, law firms, clinics, small
          associations — INCLUDING the legal form ("Horizon Conseil SARL").
- `ADDR`  a postal address of a person or private organisation: street + number,
          postal code, city when part of that address. One span may cover the
          whole multi-line address; put a trailing country name in OPT instead.
- `ID`    identifier tied to a person or private company: national ID / social
          security / tax ID / passport / driving licence / health-insurance
          number, patient or medical-record number, employee number, customer
          or account number, policy number, card number, company registration
          number (SIREN/SIRET, HRB, KvK, NIF/CIF…), VAT number of a party.
- `IBAN`  a full IBAN.  `PHONE`  a phone/fax number.  `EMAIL`  an e-mail address.
- `DOB`   a date of birth (anyone's, including children's).

NEUTRAL (neither leak nor false positive):
- `OPT`   honorifics/titles next to a name (M., Mme, Dr., Me, Maître, Herr, Frau,
          Sr., Dña., Avv., Dott., dhr., mevr.), standalone city/country names
          outside an address ("Lyon, le 3 mars"), courts, ministries, tax/social
          authorities, big public brands and banks (Google, BNP Paribas), BIC codes.
- `REF`   document references: invoice/order/contract/case/docket numbers,
          transaction references on bank statements, file numbers.
- `DATE`  any ordinary date that is NOT a date of birth (contract date, due
          date, transaction date, hearing date).

MUST NOT be redacted (trap words — tag them explicitly):
- `NEG`   words an over-eager anonymizer wrongly hides: drug names, diseases and
          diagnoses, lab tests/abbreviations (LDL, HbA1c, TSH), product and
          service words, contract-type nouns and section headings in CAPITALS
          ("DIENSTLEISTUNGSVERTRAG", "CONDITIONS GÉNÉRALES"), legal boilerplate
          terms, generic role nouns ("the Tenant", "le Prestataire"),
          common-word homographs used as ordinary words (rose the flower, grande
          the adjective), article/section numbers ("Art. 847", "§ 148"), amounts.
          Tag 8–15 NEG traps per document (tag the word/phrase itself).

Everything else is plain text (also must not be redacted; it is scored).
Amounts of money stay plain text (or NEG) — never ID.

## Required documents (7 per language, ids `<lang>01_…` … `<lang>07_…`)
1. Contract: party blocks with names in CAPITALS and addresses, a company
   party with legal form + registration no. + representative, a numbered
   witness list ("1. …\n2. …"), and a two-column signature block (`cols`).
2. Invoice: supplier letterhead (company, address, phone, email, VAT/registration
   id), client block, line-item table, totals, IBAN + BIC, payment terms.
3. Bank statement: account holder, address, account no., IBAN; a DENSE table
   of 25–35 transactions (date, merchant/payee incl. some person names in
   transfers, reference, amount, balance). Ordinary dates are `DATE`.
4. Medical record / clinic letter: patient name + DOB + health-insurance ID +
   patient number, doctors with titles, diagnoses/drugs/lab values as NEG,
   clinic name + address, a next-of-kin contact.
5. HR/employment letter: employer, employee (surname-first somewhere),
   employee number, national ID/social security number, salary (plain),
   manager, HR contact phone/email.
6. Legal correspondence: an e-mail thread (From/To/Cc headers with emails) or a
   lawyer's letter to a court — case number (REF), lawyers, opposing party,
   court (OPT), client company.
7. LONG DENSE PAGE: `"dense": true`, ONE page, 1,500–1,900 words (meeting
   minutes, due-diligence memo, witness statement…). Scatter ≥ 25 PER
   mentions across the whole page INCLUDING the last 20 %, repeat some names
   in short form (surname only, "Mr Carter" → `OPT|Mr` + `PER|Carter`), and
   include plenty of NEG traps and plain prose.

Spread these HARD CASES over the 7 documents (each at least twice per language):
names in CAPITALS; SURNAME-first; particles; hyphenated surnames; honorifics;
a name split across a line break (`[[PER|Jean-Baptiste\nDUPONT]]` inside a
`lines` or `cols` block); initials; names that are common words (Rose, Mark,
Bill, Grande, Klein, Blanc, Weiss, Rosa, Leão, de Vries…); numbered witness
lists; the country's own national-ID formats; IBAN/BIC; national phone
formats (with and without country code); e-mails; postal addresses; DOB vs
ordinary dates; companies with legal forms. Also include some person names
inside running prose mid-sentence, not only in labelled fields.

Targets per language: ≥ 120 sensitive spans total, ≥ 60 of them PER; ≥ 60 NEG.
Pages at 10 pt hold ~500 words; split longer documents into pages yourself.

## Verify (mandatory, iterate until clean)
The writer ran a verifier (in promptShield's repository; it renders the PDFs
with `scorer/render.py` and loads them through the app's PDF loader) that
aligns every label with the extracted text, and had to reach `ALL ALIGNED`
with no page overflow. The published scorer repeats the alignment on every
run: an unaligned label shows up in its output and makes that document
unverifiable.
