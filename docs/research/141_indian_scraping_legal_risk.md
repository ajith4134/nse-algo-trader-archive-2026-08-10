# Indian Legal Risk: Personal, Non-Distributed Scraping of Full Article Bodies from Indian Financial News Sites

**Date:** 2026-07-26
**Scope:** Facts-only legal-risk research for a PERSONAL, non-commercial, non-distributed automated tool that fetches full article bodies (not just RSS headlines) from Economic Times, LiveMint, Moneycontrol, and Business Standard, whose ToS prohibit automated scraping, and which may log into the user's own paid subscription. This is not legal advice — it reports what statutes, ToS doctrine, and case law say, for the user's own risk-acceptance decision. The user has already accepted the risk of proceeding; this document exists to make the picture complete, not to gate the build.

---

## Bottom line up front

There is **no Indian criminal or civil case squarely holding that personal, non-redistributed scraping of a public webpage is illegal.** The two Indian cases on point either (a) turned on **republication** of scraped content on a competing site (OLX v. Padawan, decided ex-parte/uncontested) or (b) is a live, unsettled 2024–2026 Delhi High Court dispute (ANI Media v. OpenAI) where the court has just held, on a preliminary-injunction motion, that **storing and using scraped news text for private, non-redistributing purposes is *prima facie* "fair dealing"** under Copyright Act §52(1)(a) — a holding directly favorable to a personal-use scraper, though not yet final (the suit proceeds to trial). Criminal exposure under IT Act §66 requires **dishonest or fraudulent intent**, which is a real hurdle the prosecution must clear and which ordinary personal research use does not supply on its face. Contract-law (ToS breach) exposure is real in the abstract but has **no reported case of an individual, non-commercial user being sued** for it in India; the only Indian scraping-adjacent suits have targeted commercial competitors and companies. Using your own paid login is a materially different — and safer — fact pattern than anonymous/bypass scraping, both because it removes any "unauthorized access" argument and (by analogy to comparable common-law reasoning) narrows what a plaintiff could even allege was "exceeded."

**Overall risk for a personal, non-distributed, non-commercial user who logs in with their own subscription: LOW-to-MODERATE**, concentrated almost entirely in **civil ToS/contract exposure** (realistically: account suspension/termination, not litigation) rather than criminal exposure. See the Risk Summary at the end for what raises or lowers this.

---

## 1. IT Act 2000 §43 (civil) and §66 (criminal)

### §43 — Penalty and compensation for damage to computer, computer system, etc. (civil)
Section 43 creates civil liability (compensation up to ₹1 crore) against anyone who, **"without permission of the owner or any other person who is in charge of"** a computer, computer system, computer network, or computer resource:
- (a) accesses or secures access to it,
- (b) downloads, copies, or extracts any data, computer database, or information (including from removable storage media),
- (c)–(j) introduces a virus/contaminant, damages it, disrupts it, denies access to an authorised user, assists unauthorised access, charges services to another's account, destroys/alters/diminishes the value of information, steals/conceals/destroys source code, etc.

This is a **civil** provision (compensation to the person affected), not automatically criminal. Its trigger phrase — **"without permission of the owner"** — is the crux of the entire scraping question and is discussed under "unauthorized access," below.

### §66 — Computer related offences (criminal)
As amended by the IT (Amendment) Act, 2008, §66 provides: **"If any person, dishonestly or fraudulently, does any act referred to in section 43, he shall be punishable with imprisonment for a term which may extend to three years or with fine which may extend to five lakh rupees or with both."**

Two things matter for this project's risk profile:
1. §66 is **parasitic on §43** — the underlying act must first fall within §43's list (e.g., "accessing … without permission" or "downloading/extracting data … without permission").
2. §66 additionally requires the act be done **"dishonestly or fraudulently"** (as defined by IPC/BNS mens rea concepts — deceit or wrongful gain/wrongful loss intent). Ordinary personal research/analysis scraping, done openly with a user's own credentials and without deceiving the site or causing it wrongful loss, does not on its face carry this intent. This is a genuine, not cosmetic, distinction — India's own case law under §66/§43 (below) involves employees stealing PINs and diverting money (Mphasis/Citibank Pune BPO fraud, 2005: IPC §§420/465/467/471 + IT Act §43(a)/§66), or bot operators using proxy IPs, forged/stolen Aadhaar-linked accounts, and CAPTCHA/OTP bypass to defraud IRCTC's Tatkal booking system (CBI cases through 2025) — i.e., fact patterns involving deception, stolen credentials, or circumvention of a technical control for gain. None resemble a single user fetching articles their subscription already entitles them to read.

### Does the fact pattern change the §43/§66 analysis?
This is the single most consequential open question, and **no binding Indian appellate authority resolves it squarely for scraping**. Legal commentary (Ikigai Law, SSRana, Law.Asia, IAPP) converges on the following unsettled but consistent reading:

- **Accessing a publicly-served webpage with no authentication bypass** (i.e., anyone with a browser can load the same URL): the strongest argument is that the site *has* given "permission" to access that resource — it served the page to the request. §43(a)/(b)'s "without permission" element is therefore hard to satisfy on pure public-page access, even though automation is used. No Indian court has issued a reasoned holding either way; commentators flag this as a genuine gap ("Section 43 doesn't specifically address scraping visible websites" — IAPP; Ikigai Law).
- **Bypassing a bot-detection/technical barrier** (CAPTCHA-solving, IP-rotation to evade blocks, forging headers to impersonate a browser where the site actively challenges and blocks bots, defeating a paywall without a subscription): this moves toward the fact patterns Indian courts and prosecutors *have* acted on (IRCTC Tatkal bot cases), and materially increases both §43 and §66 exposure, because it supplies the "without permission" element more convincingly (the site affirmatively tried to exclude you and you defeated that) and starts to look like the kind of deliberate circumvention that supports "dishonest" intent.
- **Logging in with your own paid subscription**: this is the safest fact pattern of the three. You are an authorised user of the site with a valid account; the site granted you a login specifically to access the content behind the paywall. There is no "unauthorized access" in the §43(a) sense — you are accessing exactly what your account is entitled to access. The realistic exposure shifts almost entirely from IT Act §43/§66 to **contract/ToS breach** (see §3–4 below), because the *manner* of access (automated fetching vs. manual browser use) may violate the ToS's "no bots/scrapers" clause even though the *access itself* is authorised.

---

## 2. Indian case law on web scraping specifically

**Confirmed: Indian scraping-specific case law is extremely thin — essentially two cases, one of them still pending — versus a larger body of unrelated hacking/fraud cases decided under the same statutory sections.**

### OLX B.V. & Ors. v. Padawan Ltd. & Ors., CS(COMM) 232/2016, Delhi High Court (Justice Rajiv Sahai Endlaw), decree dated 15 December 2016 — **primary source read directly from the Delhi High Court's own PDF for this report**.
- OLX sued 13 defendants (Padawan Ltd., a UK-based classifieds operator, plus ISPs joined as proforma defendants) to restrain **"automated or manual means to scrape any data including commercial data pertaining to the plaintiffs' website,"** pleaded as breach of ToS **and** "trespass to chattel."
- What actually happened: Padawan had copied OLX listings/photos and **republished them on its own competing classifieds site** ("thegooddeal.in").
- Padawan never contested the suit; by the time of the final order it had already shut the infringing site down (per its own letter to OLX's counsel) and was proceeded against **ex parte**.
- The court granted only the relief OLX ultimately pressed for — a **permanent injunction confined to copyright and trademark infringement** (paragraph 48(a)–(d) of the plaint) — following *Satya Infrastructure v. Satya Infra & Estates* (2013) on ex-parte relief.
- **Important nuance for this project**: because the case was uncontested, the court **never actually reasoned through or ruled on** the ToS-breach or "trespass to chattel" theories that were pleaded — it granted an agreed/uncontested injunction on the copyright/trademark grounds alone. Trespass to chattel is a common-law doctrine with no clear independent footing in Indian statute; its status in India remains untested by any *contested* judgment. The case is therefore real precedent that **republishing scraped commercial listings as your own competing content is copyright/trademark infringement** — it is **not** authority that scraping-for-private-use, without republication, is unlawful.

### ANI Media Pvt. Ltd. v. OpenAI OpCo LLC & Anr., CS(COMM) 1028/2024, Delhi High Court (Justice Amit Bansal) — **live case; most relevant and most current precedent, ruling dated 24 July 2026**.
- ANI (a major Indian news agency) alleges OpenAI's counsel "scrape[d] data, ma[de] copies, store[d] it, and then use[d] it for training" ChatGPT from ANI's website content, arguing that the underlying scraping/storage was itself infringing regardless of whether the ultimate training use was fair.
- OpenAI's defence (Senior Advocate Kapil Sibal): it accessed material through legitimate/lawful channels, did not breach any paywall, and did not rely on pirated sources.
- ANI's counsel (Senior Advocate Chander Lal) stressed that Indian copyright law uses a **closed-list "fair dealing"** regime (unlike the US's open-ended "fair use"), and that copyright protects the *expression* of facts, not facts themselves.
- **Ruling, 24 July 2026**: the Delhi High Court **denied ANI's preliminary injunction**, holding OpenAI **"likely did not infringe"** ANI's copyright. The court found it constitutes **prima facie fair dealing under §52(1)(a)** to use copyrighted works (including news content) to train AI models, and — directly on point for this project — held that **"the alleged storage of copies during training also fell within fair dealing."** The court's reasoning drew comparisons to the US *Bartz*, *Kadrey*, and *Google Books* lines of cases.
- **Caveat**: this is a **preliminary-injunction ruling, not a final judgment on the merits** — the underlying suit proceeds to trial, and could still be appealed or reversed later. It is nonetheless the single most on-point, most current Indian judicial statement that (a) scraping news content and (b) storing the scraped copies for a private/analytical (non-republishing) downstream use can fall within India's fair-dealing exceptions.

### No case found on personal/individual non-commercial scraping.
Targeted searches for scraping disputes involving Naukri.com, Quikr, JustDial, MakeMyTrip, or similar Indian platforms returned **no reported cases** — Indian scraping litigation to date has been between commercial entities over competitive/republication harms (OLX) or over AI-training use at commercial scale (ANI v. OpenAI), not against individual personal users.

### Non-Indian anchors (clearly non-binding, cited only for contrast)
- **hiQ Labs v. LinkedIn (US, 9th Circuit 2019; on remand; settled Dec. 2022)**: the 9th Circuit held that scraping data from a **publicly accessible** page (logged out, no password) does not violate the US Computer Fraud and Abuse Act. However, on remand the district court held LinkedIn's user-agreement anti-scraping clause **enforceable as a breach-of-contract claim independent of CFAA**, and the case ultimately settled with a **$500,000 judgment against hiQ**, a permanent injunction, and a data/algorithm-deletion order. Net lesson (US-specific, illustrative not authoritative in India): even where scraping public data escapes "unauthorized access" hacking statutes, **ToS/contract-breach exposure survives** as a separate, real track.
- **Van Buren v. United States (US Supreme Court, 2021)**: narrowed the CFAA's "exceeds authorized access" language to mean accessing areas of a system that are **off-limits to you**, not merely misusing access you are otherwise entitled to (e.g., logging in with your own valid credentials and using the access for a purpose the site disapproves of). US law, not binding in India, but conceptually parallel to the "own paid login" question in §4 below.
- **Ryanair Ltd. v. PR Aviation BV, CJEU Case C-30/14 (EU, 2015)**: held that even where a database has no EU sui generis database right or copyright, **a website's contractual terms of use can still validly prohibit automated/commercial data extraction**, and such contractual prohibitions are enforceable independent of IP law. EU law, non-Indian, but relevant as the clearest global precedent that **ToS restrictions on scraping have independent contractual force even absent any IP claim** — a dynamic Indian contract law (see §3) is generally understood to mirror.
- India has **no sui generis database right** equivalent to the EU Database Directive — Indian courts protect databases only via ordinary copyright ("literary work," requiring some skill/judgment in compilation) or via contract/ToS, not via a separate database right.

---

## 3. Contract-law (ToS breach) exposure for a personal user

- **Indian electronic contracts are generally enforceable.** §10A of the IT Act 2000 validates contract formation by electronic means without special formality requirements, and the Indian Contract Act, 1872 governs validity (offer, acceptance, free consent, lawful consideration/object).
- **Clickwrap** (explicit "I Agree" tied to visible terms) is **generally enforceable** in Indian courts when notice is clear and conspicuous and assent is an affirmative act — supported by *Trimex International FZE v. Vedanta Aluminium* (SC, 2010, on e-contract validity generally), *HDFC Bank Ltd. v. [subscriber]* (Delhi HC, 2016), and *DLF Ltd. v. Manmohan Lowe* (2017).
- **Browsewrap** (terms merely linked in a footer, no affirmative click) is **considerably weaker** and contested — Indian commentary applies *consensus ad idem* principles from *Avitel Post Studioz v. HSBC* (2020) to argue that without conspicuous notice, no true contract may have formed. Most major financial-news sites' anti-scraping clauses live inside standard clickwrap-style Terms of Use accepted at signup/registration (which is the relevant form here, given the user has or would have a paid account), so treat them as the *stronger*, likely-enforceable, clickwrap category rather than assuming the weaker browsewrap treatment applies.
- **Remedies for ToS breach** in Indian contract law would ordinarily be **civil** — damages (which a personal, non-commercial user causes essentially none of, since nothing is redistributed or monetized) and/or **injunctive relief** (an order to stop) and, most realistically and far short of litigation, **account suspension/termination** under the ToS's own enforcement clause. No Indian precedent establishes criminal liability from ToS breach alone.
- **No Indian precedent for suing an individual, non-commercial user over ToS-breach scraping.** Every Indian scraping dispute identified (OLX v. Padawan; ANI v. OpenAI) was commercial-entity vs. commercial-entity, over competitive harm or commercial AI-training use at scale — not an individual doing personal research. This does not make a personal user immune, but it means there is **no case establishing that such litigation is realistic or has ever been pursued** against someone in this user's position. Realistically, a subscription-based commercial publisher's primary lever against an individual is **technical/contractual** (rate-limit, CAPTCHA-gate, or terminate the account), not litigation, given the near-zero damages a court could find.

---

## 4. Does logging in with your own paid subscription change the exposure?

Yes, materially, in the user's favor, on two of the three legal tracks:

- **IT Act §43/§66 (unauthorized access)**: using your own valid credentials to access content your subscription entitles you to removes the core "without permission" element that §43(a)/(b) require. You are not accessing anything you weren't given permission to access — you are simply automating the *retrieval mechanics* of content you're already entitled to view. This is conceptually close to the reasoning in *Van Buren v. United States* (non-Indian, but persuasive by analogy): using authorized access for a purpose the grantor dislikes is different in kind from breaching a technical barrier to reach something off-limits. No Indian court has ruled on this point in a scraping context, but the statutory text (turning on "permission," not "manner of use") supports the same reading.
- **Contract/ToS breach**: this is where the *manner* of access (automated fetch vs. manual browsing) still matters — a paid subscriber's login gives them authorized *access*, but the site's Terms of Use can still separately prohibit *automated* access as a condition of that access, and using bot-driven retrieval while logged in can still breach that clause even though there is no "unauthorized access" in the IT Act sense. So: own-login **eliminates the IT Act §43/§66 exposure almost entirely**, but **does not eliminate ToS/contract exposure** — it just moves the entire risk into the contract track, which (per §3) carries realistic remedies of account termination/civil injunction rather than criminal liability, and for which no individual has been sued in India to date.
- **Practical corollary**: logging into your own account converts what would otherwise be a genuinely ambiguous "unauthorized access" question into a clean contract question — a real improvement, since contract exposure for a non-commercial, non-redistributing individual is the lowest-severity, best-precedented (in the user's favor, via absence of any adverse case) branch of the whole analysis.

---

## 5. Copyright/database-right angle on storing fetched article text for personal analysis

- **India Copyright Act, 1957, §14** grants the copyright owner (the publisher) exclusive rights to reproduce the work, including storing it electronically.
- **§52(1)(a)** creates a **fair dealing** exception (not a US-style open "fair use" — India's list is closed/enumerated) covering, among other clauses:
  - **§52(1)(a)(i)** — fair dealing with a literary work **for the purposes of private use, including research**;
  - **§52(1)(a)(ii)** — fair dealing **for criticism or review**, of that work or another;
  - (a further, separately-numbered clause covers reporting of current events, including via broadcast/press summary — the exact sub-clause text was not independently re-verified in this pass beyond secondary summaries, but its existence and general scope is well-established in Indian copyright practice).
- **This is squarely the provision the Delhi High Court just applied, on 24 July 2026, in ANI Media v. OpenAI** — holding that using copyrighted news content (via scraped/stored copies) for a private/analytical downstream purpose is **prima facie fair dealing**, including the **storage** step itself, not just the ultimate use. That is the single most relevant, most current piece of authority for this project's specific fact pattern (storing full article text for personal quantitative/analytical use, not republishing it) — though again, it is a preliminary ruling in a case that continues to trial, not a final, appeal-proof precedent.
- **No separate database right exists in India** (unlike the EU) — so there is no independent "sui generis" exposure from compiling a database of stored articles; any exposure would run through ordinary copyright (§14 reproduction right) subject to the §52 fair-dealing exceptions above.
- **Storing for personal, non-redistributed research/analysis use maps well onto §52(1)(a)(i)'s "private use including research"** — this is a considerably stronger position than the OLX v. Padawan fact pattern (republishing on a competing public site), which is the one thing Indian precedent has actually punished.

---

## 6. Practical risk-reduction that does not defeat the purpose

These are not legal requirements under any binding Indian rule, but they track exactly what the case law and commentary above flag as the factors that would push a fact pattern toward the "риск" (bad) end of the spectrum if absent, or keep it toward the safe end if present:

- **Honor `robots.txt`.** It has **no independent legal force** in India (or generally) — "not a law, not a contract, not an enforceable directive" — but ignoring it is the kind of fact a court can treat as evidence of bad faith in a scraping dispute (cf. the US *eBay v. Bidder's Edge* reasoning, non-Indian but illustrative), whereas honoring it costs nothing and removes that evidentiary hook entirely.
- **Rate-limit aggressively** (mimic a slow human reader, not a bulk crawler) — reduces any argument of "disruption"/"denial of service" under IT Act §43(e)/(f), and reduces the chance of triggering the site's own bot-detection into an active technical confrontation (which is the fact pattern that has actually drawn Indian prosecutorial attention, e.g., IRCTC-style bot cases).
- **Never bypass CAPTCHA, WAF/bot-detection challenges, or paywalls you have not paid for.** This is the single clearest line between "unsettled/low-risk" and "the fact pattern Indian authorities have actually acted on" (IRCTC Tatkal bot prosecutions all involve captcha/OTP bypass or stolen credentials).
- **Use only your own paid, legitimately-obtained login** where a subscription gates the content — never shared/purchased/stolen credentials, never credential-stuffing.
- **Personal use only; never redistribute, republish, resell, or make the stored corpus available to any other person or the public**, in any form (this is precisely what turned OLX v. Padawan into a losing fact pattern for the defendant, and precisely what ANI v. OpenAI's favorable July 2026 ruling turned on being absent).
- **Don't circumvent explicit technical anti-bot measures** (spoofing to defeat an active block, rotating IPs specifically to evade a rate-limit ban) — doing so supplies exactly the "without permission" and "dishonest" elements that §43/§66 require and that are otherwise largely absent from this fact pattern.
- **Keep the stored data for internal analysis, not as a substitute product** — don't build anything that could be characterized as a competing news aggregator or a redistribution channel, since that is the one theory Indian courts have actually enforced against.
- **Comply with the site's own account-level terms if using a login** — i.e., don't do things the account terms expressly forbid beyond scraping itself (sharing the account, exceeding seat limits, etc.), since that stacks additional, unrelated breach theories onto the automated-access question.

---

## Risk Summary (plain language)

**For a personal, non-distributed, non-commercial individual user who (a) uses their own legitimately-paid subscription login where applicable, (b) does not bypass CAPTCHA/bot-detection/paywalls, (c) rate-limits reasonably, and (d) never republishes or redistributes the stored content: overall risk is LOW.**

- **Criminal risk (IT Act §66):** Very low. Requires "dishonest or fraudulent" intent on top of an underlying §43 act; ordinary personal-research scraping via your own login supplies neither element cleanly, and every Indian §43/§66 case identified involves deception, stolen credentials, or defeated technical controls (Mphasis/Citibank BPO fraud; IRCTC Tatkal bot cases) — a fundamentally different fact pattern.
- **Civil "unauthorized access" risk (IT Act §43):** Low-to-negligible when using your own account and not bypassing any technical barrier; the "without permission" element is hard for a publisher to establish against an authorized, paying subscriber. Rises sharply — into MODERATE/HIGH territory — the moment any CAPTCHA/bot-detection/paywall-bypass is used, or if credentials aren't the user's own legitimately-obtained ones.
- **Copyright risk:** Low for storage/personal-analytical use, per the persuasive (if not yet final) 24 July 2026 Delhi HC ANI v. OpenAI ruling applying §52(1)(a) fair dealing to exactly this kind of scrape-and-store-for-private-use pattern. Rises sharply — into HIGH territory — the moment any content is republished, redistributed, resold, or used to build a competing product (OLX v. Padawan is the cautionary precedent).
- **Contract/ToS breach risk:** MODERATE in the abstract (clickwrap ToS with anti-scraping clauses are generally enforceable in India, and automated access likely does breach them even when the underlying access is authorized via login) but LOW in practical/enforcement terms — no Indian case has ever been brought against an individual, non-commercial scraper; realistic consequence is account suspension or termination, not litigation, given the near-zero provable damages from personal use.

**What would raise the risk:** bypassing CAPTCHA/WAF/bot-detection; using shared, purchased, or another person's credentials; scraping at a volume/rate that could plausibly degrade the site's service; republishing, redistributing, or commercializing any of the stored content in any form, including sharing the dataset with others; building something a court could characterize as a competing product.

**What keeps the risk low:** own paid login, no technical-barrier bypass, conservative rate-limiting, `robots.txt` honored where practical, strictly personal/internal use with no redistribution, and treating the corpus as raw material for private analysis rather than as republished content.

---

## Sources

**Primary (read directly / official):**
- [OLX B.V. & Ors. v. Padawan Ltd. & Ors., CS(COMM) 232/2016 — Delhi High Court order dated 15.12.2016](https://delhihighcourt.nic.in/app/showlogo/246267_2016.pdf/2016) (fetched and read in full as PDF for this report)
- Information Technology Act, 2000, §43 and §66 (as amended 2008) — text corroborated via [Advocatekhoj bare act mirror](https://www.advocatekhoj.com/library/bareacts/informationtechnology/) and cross-checked figures (₹5 lakh fine, "dishonestly or fraudulently") against multiple independent secondary summaries
- Copyright Act, 1957, §52(1)(a) — text corroborated via secondary bare-act mirrors; operative application confirmed via the ANI v. OpenAI ruling below

**Secondary — reputable legal/news (India):**
- [Bar and Bench — "OpenAI did not violate copyright laws by using ANI news to train ChatGPT: Delhi High Court" (24 Jul 2026)](https://www.barandbench.com/news/litigation/openai-did-not-violate-copyright-laws-by-using-ani-news-to-train-chatgpt-delhi-high-court)
- [chatgptiseatingtheworld.com — detailed writeup of the 24 Jul 2026 Delhi HC ANI v. OpenAI ruling, incl. §52(1)(a) reasoning and "storage … fell within fair dealing" holding](https://chatgptiseatingtheworld.com/2026/07/24/india-high-court-rules-openai-did-not-infringe/)
- [LawChakra — "ANI vs OpenAI: Copyright Over AI Training" (procedural background, ANI's and OpenAI's counsel arguments)](https://lawchakra.in/high-court/ani-vs-openai-copyright-over-ai-training/)
- [World Trademark Review — "OpenAI Faces Data Scraping Allegations in India's First-Ever Generative AI Copyright Infringement Suit"](https://www.worldtrademarkreview.com/article/openai-faces-data-scraping-allegations-in-indias-first-ever-generative-ai-copyright-infringement-suit)
- [Economic Times — "HC permanently stops UK portal from copying OLX content, logo" (2016)](https://economictimes.indiatimes.com/small-biz/startups/hc-permanently-stops-uk-portal-from-copying-olx-content-logo/articleshow/56185489.cms)
- [The Hindu — "HC restrains UK-based portal from copying contents of OLX"](https://www.thehindu.com/news/cities/Delhi/hc-restrains-ukbased-portal-from-copying-contents-of-olx/article8481577.ece)
- [Ikigai Law — "Legality of Data Scraping in India"](https://ikigailaw.com/article/263/legality-of-data-scraping-in-india) (source for OLX v. Padawan characterization and hiQ contrast)
- [IAPP — "Scraping Public Data in India: Innovation Enabler or Privacy Threat?"](https://iapp.org/news/a/scraping-public-data-in-india-innovation-enabler-or-privacy-threat-) (DPDPA ambiguity on public data)
- [Law.Asia — "Data Scraping Consent and India's DPDPA Exemption"](https://law.asia/india-data-scraping-regulation/)
- [SSRana — "Web Scraping and Personal Data: Legal and Ethical Boundaries in AI"](https://ssrana.in/articles/web-scraping-and-personal-data-legal-and-ethical-boundaries-in-ai/)
- [Medianama — "Experts Concerned About MeitY's Stance On Web Scraping To Train AI Models" (Feb 2025)](https://medianama.com/2025/02/223-experts-concerned-about-meitys-stance-on-web-scraping-to-train-ai-models/)
- [blog.iPleaders — "Data Scraping and Its Legality"](https://blog.ipleaders.in/data-scraping-legality/)
- [blog.iPleaders — "Enforceability of Clickwrap Agreements in India: All You Need to Know"](https://blog.ipleaders.in/enforceability-of-clickwrap-agreements-in-india-all-you-need-to-know/) (Trimex International v. Vedanta Aluminium; HDFC Bank v. Kumar; DLF v. Manmohan Lowe)
- [Mondaq — "Clickwrap, Browsewrap, and Negotiated SaaS Contracts: Enforceability in India"](https://www.mondaq.com/india/contracts-and-commercial-law/1670160/clickwrap-browsewrap-and-negotiated-saas-contracts-enforceability-in-india) (Avitel Post Studioz v. HSBC on consensus ad idem)
- Mphasis/Citibank Pune BPO fraud case (2005), IPC §§420/465/467/471 + IT Act §43(a)/§66 — corroborated across multiple secondary sources (thelaw.institute, apnilaw.com, blog.iPleaders, lawfullegal.in)
- IRCTC Tatkal-booking bot/CAPTCHA-bypass prosecutions (CBI cases through 2025), IT Act §43/§66 — corroborated across Hindustan Times, The Hindu, ABP Live, India Today reporting; specific matter *Ajay Garg v. CBI* (2025) via Indian Kanoon docket reference

**Non-Indian anchors (labeled, cited only for contrast — NOT Indian law):**
- **US**: *hiQ Labs, Inc. v. LinkedIn Corp.*, 9th Cir. 2019 (CFAA holding on public-page scraping), on-remand district court ruling (Nov. 2022) enforcing LinkedIn's ToS as a separate breach-of-contract claim, and the reported Dec. 2022 settlement ($500,000 judgment, injunction, data deletion)
- **US**: *Van Buren v. United States*, 593 U.S. 374 (2021) — Supreme Court narrowing of CFAA "exceeds authorized access" to gate-based (not purpose-based) restrictions
- **EU**: *Ryanair Ltd. v. PR Aviation BV*, CJEU C-30/14 (2015) — contractual anti-scraping terms enforceable independent of database/copyright protection

## What this report did not cover
- Final/appellate disposition of ANI Media v. OpenAI (case continues to trial as of this ruling; outcome could change)
- Full statutory text of Copyright Act §52(1)(a)'s "reporting of current events" sub-clause (existence and general scope confirmed via secondary sources; exact clause letter/number not independently re-verified against a primary bare-act text in this pass)
- DPDPA (Digital Personal Data Protection Act, 2023) in depth — noted as a parallel, still-unsettled-in-practice regime primarily aimed at *personal data of individuals* (bylines/comments could theoretically qualify) rather than at journalistic article text itself, and therefore treated as secondary to the Copyright Act and IT Act analysis above, not a primary risk driver for this specific use case
- Any criminal complaint or FIR actually filed against an individual for personal-use news scraping in India (none was found to exist)
- Cross-jurisdictional exposure if the sites' servers, cloud infrastructure, or corporate registration create a non-Indian forum/choice-of-law angle (out of scope — this report is India-law-focused per the request)
