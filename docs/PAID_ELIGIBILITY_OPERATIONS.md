# IBROWS — one-off scholarship eligibility check: internal operating guide

**Package:** MK5,000 one-off Scholarship Eligibility Check. This is **not** the separate scholarship shortlist, application support or monthly subscription. Do not conflate amounts or scopes.

## Core separation of responsibilities

1. **Verified payment**: the only source of truth is a ledger receipt posted through authenticated administrator payment confirmation. Customer statements, payment screenshots and generic WhatsApp chat history cannot activate paid service.
2. **Service work stage**: a separate `scholarship_eligibility_cases` case row is created only when the administrator first confirms a real step. It never creates or modifies a payment.
3. **CRM enquiry stage**: NEW/CONTACTED/CLOSED describes correspondence, not payment status and not eligibility-work completion.
4. **AI conversation**: `START ELIGIBILITY` or `CONTINUE ELIGIBILITY` supplies intake questions only for a verified paid one-off service. It does not claim eligibility, a scholarship award, admission, or a submitted application.
5. **Admin delivery**: `/admin/eligibility/<lead_id>` lets staff copy the intake, open IBROWS Inbox, and confirm successive work stages. Do not check a step unless it actually happened. All changes are recorded in `lead_activity`.

## One-off client workflow

- Check the selected package price, receipt total, currency and reference; **never register payment twice**.
- Read the client's previous messages before asking intake questions. Reuse supplied goals, country preferences, target intake and funding preference. Do **not** confuse clients who happen to share a first name.
- From the paid CRM lead, tap **Open Paid Eligibility Work Queue**.
- Use **Copy intake message**, open the IBROWS Inbox, and send it. Copying alone does **not** send a message. Alternatively, the client can initiate the standard intake by messaging `START ELIGIBILITY`.
- After actually sending the intake, confirm **Mark intake message actually sent**.
- Once academic details are received, confirm **Start assessment**, review degree transcript and key economics/mathematics modules, graduation date, English proficiency and professional experience. Do not solicit bank PINs, OTPs or ID numbers.
- Use official programme pages and record why an option is eligible, uncertain or ineligible; distinguish **admission** from **scholarship funding**. Cite official course eligibility and deadlines, and note when no new call is published.
- Independently check the analysis; confirm **Ready for delivery** only when a reviewed report is prepared.
- Send the finished assessment, then and only then confirm **Delivered**. Close the CRM enquiry separately when appropriate.
- State a turnaround time only if IBROWS has actually agreed one with the client. Otherwise acknowledge receipt and explain the next step without inventing a deadline.

## First real service: learning points

- The first one-off customer paid MK5,000, but old AI-generated notes still said NOT_PAID. These were repaired and archived separately; **ledger confirmation always wins**.
- The dashboard originally counted paid value as an unpaid pipeline opportunity; it now subtracts verified same-currency payments.
- The WhatsApp client did not yet have a reliable next step after payment, prompting this explicit intake command and work queue.
- No admission assessment can be final until academic documentation is received. Never mark work delivered because a payment was received.
- Current scholarship research must be reverified before a client deliverable, particularly early-2027 deadlines.

## Official research starting points (verify again before delivery)

- Erasmus Mundus Joint Masters: https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters
- EPOG admission and coursework: https://www.epog.eu/admission-and-scholarships/admission/
- EGEI economics prerequisites: https://www.master-egei.eu/faq-application/
- University of Luxembourg Master in Finance and Economics: https://www.uni.lu/fdef-en/study-programs/master-in-finance-and-economics/admissions/
- Chevening Malawi: https://www.chevening.org/scholarship/malawi/

## Validation

The no-network workflow `paid-eligibility-regression.yml` compiles the application and tests the real `receive_webhook` function under mocked WhatsApp messages and payment snapshots. No external messages, API keys or production database queries are needed during these tests. Recheck live Render logs and ledger totals after deployments.

**Never include identifiable customer academic results in public repositories, CI logs or sample test fixtures.**
