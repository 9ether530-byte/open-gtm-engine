# OpenGTM CRM

Plain-Markdown CRM generated from the local SQLite database. No database is required to read this file.

Generated: 2026-11-12T21:01:18.565750+00:00

## Accounts

### DemoWorks

- Dan Demo — Head of Growth — score 40 (funding (+25), role fit: Head of Growth (+15))
  - Email: dan@example.test
  - LinkedIn: https://www.linkedin.com/in/dan-demo
  - X: @dandemo
  - Notes: Fictional sample lead

### Example Analytics

- Ada Example — Founder — score 65 (hiring (+25), funding (+25), role fit: Founder (+15))
  - Email: ada@example.test
  - LinkedIn: https://www.linkedin.com/in/ada-example
  - X: @adaexample
  - Notes: Fictional sample lead

### Placeholder Studio

- Eve Placeholder — Marketing Manager — score 0 (no signals)
  - Email: eve@example.test
  - LinkedIn: https://www.linkedin.com/in/eve-placeholder
  - X: @eveplaceholder
  - Notes: Fictional sample lead

### Sample Roofing Co

- Ben Sample — Director of Operations — score 35 (post_engagement (+20), role fit: Director of Operations (+15))
  - Email: ben@example.test
  - LinkedIn: https://www.linkedin.com/in/ben-sample
  - X: @bensample
  - Notes: Fictional sample lead

### Testbridge Labs

- Cara Test — VP Sales — score 55 (competitor_customer (+15), hiring (+25), role fit: VP Sales (+15))
  - Email: cara@example.test
  - LinkedIn: https://www.linkedin.com/in/cara-test
  - X: @caratest
  - Notes: Fictional sample lead

## People

- Ada Example (Example Analytics, Founder) — signals: hiring, funding — score 65
- Cara Test (Testbridge Labs, VP Sales) — signals: competitor_customer, hiring — score 55
- Dan Demo (DemoWorks, Head of Growth) — signals: funding — score 40
- Ben Sample (Sample Roofing Co, Director of Operations) — signals: post_engagement — score 35
- Eve Placeholder (Placeholder Studio, Marketing Manager) — signals: none — score 0

## Activities

### Sequence 1 — Ada Example (Outreach — Ada Example)
- Step 1 [linkedin] connection_request: approved — approved by Rashad
- Step 2 [linkedin] follow_up: draft
- Step 3 [email] email: draft
- Step 4 [x] x_dm: draft

- Reply (lead 1, linkedin, replied): Interested

## Tasks

- [ ] Send step 1 (linkedin) in sequence 1 manually, then mark sent
- [ ] Review + approve step 2 (linkedin) in sequence 1
- [ ] Review + approve step 3 (email) in sequence 1
- [ ] Review + approve step 4 (x) in sequence 1
