# India hosting and credit options

Reviewed against the linked official pages on **24 October 2026**. Offers, eligibility and capacity can change; an advertised credit is not an allocation to this project. No application, purchase or server provisioning has been performed.

## Practical deployment choice

Use one India-region Linux VM with a public IPv4 address and configurable inbound UDP for the website, Python API/RTC agent and self-hosted LiveKit. Keep one API worker and the persistent usage-ledger volume. A starting allocation of 4 vCPU, 8 GB RAM and 40 GB SSD is a planning estimate for a small demonstration, **not a tested capacity guarantee**. Evon model memory is additional and is not included in this CPU-server estimate.

The prepared [single-VM deployment](../deploy/production/README.md) uses three DNS hostnames on that VM and generates its own LiveKit credentials. No LiveKit Cloud account or credits are required. The normal server, public IP, bandwidth and domain can still cost money.

For Evon, first check whether your Gnani account has approved hosted-beta access. If approved, obtain its actual endpoint, model identifier, authentication instructions and credit coverage. The adapter currently expects an OpenAI-compatible chat-completions contract; a marketing announcement does not establish compatibility. If the supplied contract differs, the provider adapter must be adjusted against that documentation. Otherwise supply a separately hosted Evon GPU endpoint. No GPU is started or model downloaded automatically. [Gnani Evon beta](https://www.gnani.ai/evon-waitlist), [Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B).

## Shortlist

| Provider or programme | Appropriate role | Verified credit/availability boundary |
| --- | --- | --- |
| **Zoho Catalyst** | A possible frontend or HTTP-service host; confirm the required product is available in the India data centre | Eligible non-commercial student projects can use up to **$250 over six months**, without a card. The app stops at the threshold; an extension requires review. This is Catalyst usage, not a general VM grant. [Student programme](https://catalyst.zoho.com/students/). |
| **Gnani AI** | Prisma STT, Timbre TTS/optional cloning; selected Evon hosted-beta accounts | Internship registration provides **5,000 programme API credits**. The public programme does not promise a VM or GPU allocation. Evon beta selection and whether those credits cover it must be confirmed separately. [Internship resources](https://www.gnani.ai/internship), [Evon beta](https://www.gnani.ai/evon-waitlist). |
| **E2E Networks** | CPU VM for LiveKit/application; separate GPU model serving | Documentation supports public networking and custom UDP security rules, making this a practical candidate. Its AI Explorer offer advertises $5,000 credits for eligible **incorporated AI startups**; it is not a general student entitlement. Higher headline tiers are usage discounts. [VM networking](https://docs.e2enetworks.com/docs/myaccount/node/manage/network/), [security groups](https://docs.e2enetworks.com/docs/myaccount/network/security_grp/), [programme](https://www.e2enetworks.com/startup-program). |
| **Yotta Shakti Studio** | Investigate an India-hosted custom Evon inference deployment | The launch offer advertises **₹10,000 for 30 days**, subject to its terms and eligibility. Confirm Evon model support, serving memory, cold-start latency and which products credits cover. This is not evidence of an included always-on LiveKit VM. [Offer and terms](https://shakticloud.ai/shakti-studio-free-ai-cloud-credits/). |
| **Yotta Yntraa / Rudra** | VM/networking or a separately approved startup programme | Yntraa documents VM public-IP/NAT networking. Verify UDP, actual India region and recurring charges. Rudra's accelerator is conditional, not an automatic student credit. [VM networking](https://docs.yntraacloud.ai/docs/Subscribers/Networking/VirtualFirewall/DeployingVNFandVMWithinVNF/), [Rudra](https://yotta.com/rudra/). |
| **IndiaAI Compute** | Apply for approved subsidised GPU/infrastructure access | Students and academia are among the eligible categories, with document verification and compute-request approval. This is subsidised access, not guaranteed free compute. [Official portal](https://compute.indiaai.gov.in/login). |
| **Neysa, Tata Communications Vayu, CtrlS** | Additional India infrastructure/GPU candidates if their plans fit | Evaluate quotations, public-IP/UDP support, GPU memory and data terms. No unconditional free student-server allocation was verified. [Neysa](https://neysa.ai/lp/gpu-cloud-platform-1/), [Vayu](https://www.tatacommunications.com/cloud-listing), [CtrlS GPU infrastructure](https://www.ctrls.com/brochure/gpu-private-cloud.pdf). |

The IndiaAI portal also lists providers such as Cyfuture, NxtGen, Sify, Jio Platforms and others. Listing is a useful discovery source, not confirmation that each provider offers a suitable student plan or this project's required network access. [Official provider list](https://compute.indiaai.gov.in/login).

## Why Zoho is not the initial all-in-one host

AppSail is a managed web-service platform. Its documented request timeout, idle shutdown and autoscaling differ from an always-running SFU and a single-owner, in-memory room agent. Public UDP exposure for LiveKit has not been established. The current code should not be deployed unchanged there as a complete RTC stack. Using Zoho for the frontend would also require explicit API origins and WebSocket routing rather than the prepared same-origin VM setup. [AppSail basics](https://docs.catalyst.zoho.com/en/serverless/help/appsail/appsail-basics/).

Catalyst documents an India data-centre endpoint; select and verify that region rather than assuming an account created on a global domain is India-hosted. Confirm product availability with Zoho. [Multi-data-centre support](https://docs.catalyst.zoho.com/en/api/introduction/multi-dc-support/).

## Before calling the deployment sovereign

An Indian company name or an India VM alone does not establish the whole processing boundary. Record the actual regions and control arrangements for frontend delivery, media/TURN, API/agent, inference, provider retention, backups, logs and administrative access. The frontend now uses system fonts and has no runtime font-CDN dependency. The current private Sites preview remains a separate static demonstration and is not proof of India-only hosting.

Keep infrastructure credit expiry, idle GPU charges and bandwidth limits visible in the provider console. The application's daily caps reserve STT/MT/TTS/enrollment units; they cannot stop a provider's idle VM/GPU bill or read an undocumented vendor balance. See [CREDIT_CONTROLS.md](CREDIT_CONTROLS.md).
