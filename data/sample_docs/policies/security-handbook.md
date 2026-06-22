# Acme Corp Information Security Handbook (Sample Demo Corpus)

> This is a fictional sample document used to populate the demo vector store.
> Replace `data/sample_docs/` with the client's real corpus before a live demo.

## 1. Access Control

All access to production systems is granted on a least-privilege basis. Employees
receive only the permissions required for their role. Access is reviewed quarterly,
and any account inactive for 90 days is automatically disabled.

Multi-factor authentication (MFA) is mandatory for all administrative access and
for any access to systems holding customer data. Hardware security keys are
preferred over TOTP applications for privileged roles.

## 2. Data Classification

Data is classified into four tiers: Public, Internal, Confidential, and Restricted.
Restricted data (including customer PII and financial records) must be encrypted at
rest with customer-managed keys and in transit using TLS 1.2 or higher.

Confidential and Restricted data may not be copied to personal devices or to
unmanaged third-party services. Exceptions require written approval from the
Security Officer.

## 3. Incident Response

Suspected security incidents must be reported to the Security Operations Center
within one hour of discovery. The on-call responder triages the incident, assigns a
severity (S1 through S4), and opens an incident record.

S1 incidents (active breach, data loss, or customer-facing outage) trigger an
immediate page to the incident commander and require a postmortem within five
business days. The postmortem must identify the root cause and at least one
preventative action.

## 4. Encryption Standards

All customer data is encrypted at rest using AES-256 with keys managed in a
dedicated key management service. Encryption keys are rotated annually and on any
suspected compromise. Plaintext secrets must never be committed to source control
or written to application logs.

## 5. Vendor Management

Third-party vendors that process Restricted data must complete a security
assessment before onboarding and annually thereafter. Vendors must maintain SOC 2
Type II attestation or an equivalent recognized standard.

## 6. Retention and Disposal

Customer records are retained for seven years to meet regulatory requirements,
after which they are securely deleted. Backup media is encrypted and destroyed via
certified media sanitization at end of life.
