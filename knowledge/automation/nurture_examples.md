# B2C Residential Solar Lead Nurturing Blueprint
### *Automated AI SMS & 14-Day Email Sequences for Leads Who Opted In But Didn't Book a Call*

---

## Executive Overview & Conversion Architecture

When a residential solar lead opts in via a utility bill breakdown, rate hike report, or solar calculator ad but **does not immediately schedule a call**, standard corporate automated follow-ups fail because they sound like aggressive, generic sales pitches. 

This nurturing system is engineered specifically for **B2C Residential Solar Businesses**. It follows the multi-channel workflow illustrated in `sequence.png`, deploying two synchronized channels:
1. **AI SMS Appointment Setter Sequence**: A 6-step conversational, low-friction SMS workflow designed to disarm defensiveness, elicit replies, uncover past intent, and guide leads directly into booking a **15-Minute Solar Utility Bill Review**.
2. **14-Day Automated Email Sequence**: A 1-email-per-day value & psychology sequence incorporating core sales reframes (Usain Bolt, Island vs. Mountain, Heavy is the Head, 4,000 Dots, McDonald's vs. Entrepreneur, and the Apology Breakup).

### Multi-Channel Lead Nurturing Workflow

**Lead Source**: Opt-In Lead (No Call Booked)

* **Channel 1: AI SMS Appointment Setter Sequence**
  * Wait 6 Minutes: Initial Opt-In SMS
  * 1-Hour Follow-Up: Context Check-In
  * 24-Hour Follow-Up: Past Intent Reframe
  * 48-Hour Follow-Up #1: Utility Rate Cap Check
  * 48-Hour Follow-Up #2: Disarming Courtesy Apology Exit

* **Channel 2: 14-Day Automated Email Sequence**
  * Day 1: The Utility Monopoly Trap
  * Day 2: Renting vs. Owning Power
  * Day 3: Local Case Study
  * Day 4: "Is Solar a Scam?"
  * Days 5–14: Core Reframes, Utility Inflation Math & Value Propositions

**Target Conversion**: 15-Minute Solar Utility Bill Review Calendar Booking
---

## Section 1: AI SMS Appointment Setter Sequence

### SMS Sequence Strategy & Tonality Guidelines
* **The 6-Minute Rule**: Delaying the first text by 6 minutes prevents the lead from perceiving the response as a robotic auto-responder, establishing human or intelligent casual AI presence.
* **Tonality**: Casual, disarming, curious, and concise. Never use corporate greetings ("Dear Homeowner", "Thank you for visiting our website").
* **Goal**: Get the homeowner to respond with their electric bill frustration or solar intent, then transition them smoothly onto the closer's calendar.

---

### Step-by-Step SMS Sequence Scripts

#### Step 1: Initial SMS (Sent 6 Minutes Post Opt-In)
* **Timing**: Wait 6 minutes after opt-in.
* **Objective**: Reconfirm opt-in with a disarming intro and extract intent.

```text
Hey {{first_name}}? It's {{rep_name}} with {{company}}. 

Looks like you checked out the utility rate breakdown for the {{city}} area—is that about right? 

Just wanted to see, what was your main intent behind looking into stopping those rate hikes for the house?
```

---

#### Step 2: 1-Hour Follow-Up SMS
* **Timing**: 1 hour after Step 1 (if no reply).
* **Objective**: Soft, conversational check-in adding context without pressure.

```text
No rush at all {{first_name}}! 

I ask because most homeowners in {{city}} reaching out are seeing their summer bills creep past $300-$400/mo. 

Were your utility bills hitting that point, or were you just exploring options for the house?
```

---

#### Step 3: 24-Hour Follow-Up SMS
* **Timing**: 24 hours after initial opt-in.
* **Objective**: Uncover past intent using the *"What was your intent back then?"* disarming reframe.

```text
Hey {{first_name}}, I know life gets crazy busy! 

You might not even remember filling out the form yesterday, but looking back... what would you say was the main thing you were hoping to change about your electric bill when you opted in?
```

---

#### Step 4: 48-Hour Follow-Up SMS (#1)
* **Timing**: 48 hours after Step 3.
* **Objective**: Educate with a low-friction micro-question about utility rate caps.

```text
Quick question {{first_name}}—did {{utility_company}} already lock in your rate tier for this year, or are you still on their variable residential schedule where prices increase every summer?
```

---

#### Step 5: 48-Hour Follow-Up SMS (#2 - Exit / Door-Opener)
* **Timing**: 48 hours after Step 4 (Day 4/5 post-opt-in).
* **Objective**: Disarming apology pattern interrupt that removes pressure and leaves the door wide open for high-conversion replies.

```text
Hey {{first_name}}, I want to apologize—I don't want to be that annoying solar guy blowing up your phone! 

I'll assume you decided to stick with {{utility_company}} for now. If rate hikes ever get out of hand down the road, feel free to text me back here. 

Wish you and the family the best!
```

---

### AI SMS Reply Handling & Decision Trees

#### Scenario A: Homeowner Asks "How much does it cost?"
* **Principle**: Disarm price shock, isolate logistics, and pivot to value review.

```text
AI Rep: "Fair question {{first_name}}! Systems are $0 upfront out-of-pocket because the state program lets you swap your electric bill for a fixed lower power payment. 

To give you an exact dollar number, it depends on your monthly kilowatt usage. Around how much was your highest electric bill this past summer?"
```

#### Scenario B: Homeowner Says "Is this a scam / bad contractor?"
* **Principle**: The Paint & Contractor Reframe.

```text
AI Rep: "I totally get why you'd ask {{first_name}}—there are definitely sloppy solar installers out there giving the industry a bad name! 

It's kind of like if a bad contractor paints a neighbor's house terribly... paint itself isn't a scam, that contractor was just sloppy. 

We only do tier-1 equipment with locked production guarantees. Would you be open to taking 5 mins to look at your actual utility usage to see if it even makes financial sense for your roof?"
```

#### Scenario C: Homeowner Says "I need to talk to my spouse first"
* **Principle**: Shift responsibility disarming reframe.

```text
AI Rep: "100% makes sense {{first_name}}! Both of you should definitely be on the same page. 

Usually, spouses just want to make sure the household budget is protected and rates don't keep jumping. 

If your spouse walked in right now and said 'Honey, I trust you 100%, do whatever is best for the family,' would you want to lock in a fixed $0 power bill, or stick with {{utility_company}}?"
```

#### Scenario D: Homeowner Says "Just email me info / send a quote"
* **Principle**: Nurture video offer & schedule lock.

```text
AI Rep: "I can definitely do that {{first_name}}! Solar quotes depend on your roof angle and monthly kWh history. 

I actually have a quick 3-minute video breakdown showing how {{utility_company}} structures their residential rate hikes in {{city}}. 

If I text you that short video now, can you watch it today so we can reconnect tomorrow for 5 mins?"
```

---

## Section 2: The 14-Day Automated Email Sequence

### Email Sequence Core Architecture
Each email addresses a specific psychological barrier, applies a proven sales reframe from the training curriculum, and provides a clear, low-friction Call To Action (CTA) to book a **15-Minute Solar Utility Review**.

```
Day  1: The Utility Monopoly Trap (Why your electric bill keeps compounding)
Day  2: Renting vs. Owning Power ($0-Down Financial Math)
Day  3: Local Case Study ($380/mo bill eliminated in {{city}})
Day  4: "Is Solar a Scam?" (Addressing sloppy contractors & bad installs)
Day  5: Net Metering & The Rate Hike Clock (Urgency & Rate Locks)
Day  6: "Heavy Is the Head That Wears the Crown" (Household budget reframe)
Day  7: The Island & The Mountain (Elevating perspective on 20-year equity)
Day  8: Blackouts, Storm Season & Grid Protection (Battery backup)
Day  9: The 180 Summer Bills Left (The 4,000 Dots Analogy applied to energy)
Day 10: McDonald's Worker vs. Energy Entrepreneur (Risk Reframe)
Day 11: Home Equity & Property Tax Shield (Building asset value)
Day 12: Usain Bolt & The Lion (Push vs. Pull motivation)
Day 13: 3-Minute Video Breakdown (Educational Nurture)
Day 14: The "I Failed You" Courtesy Apology (Breakup Pattern Interrupt)
```

---

### Day 1 Email: The Utility Monopoly Trap
* **Subject**: The real reason your {{utility_company}} bill jumped last summer
* **Preview Text**: Why paying a monthly electric bill is like renting an apartment forever...
* **Framework**: Mapping Current Process & Logical Certainty.

```markdown
Hey {{first_name}},

When your electric bill arrives in the mail every month, do you ever feel like you're throwing money into a black hole?

Here is the uncomfortable truth most homeowners in {{city}} never realize:

When you pay {{utility_company}}, you are trapped in a **Utility Rent Monopoly**. 

You pay them every single month, yet you build **$0 equity** in your home's energy infrastructure. To make matters worse, {{utility_company}} retains 100% control over your pricing. When they decide to raise rates by 8%, 12%, or 15% next summer... you have to pay it, or they turn off your lights.

Imagine if your landlord raised your house rent by 10% every single year without asking for your permission. You'd move out immediately, right?

So why tolerate it with your electricity?

There is a simple alternative: **Power Ownership.**

By swapping your variable utility bill for a fixed tier-1 solar ownership plan, you lock in your monthly energy cost permanently at $0 out-of-pocket upfront.

Want to see what your home's locked energy rate looks like compared to {{utility_company}}'s 5-year rate projection?

👉 **[Click here to claim your 15-Minute Solar Utility Bill Review]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 2 Email: Renting vs. Owning Power
* **Subject**: Renting electricity vs. Owning your power (The $0-Down Math)
* **Preview Text**: How to convert your monthly electric liability into a fixed home asset...
* **Framework**: Fixed Asset Equity vs. Unrecoverable Rent.

```markdown
Hey {{first_name}},

Let's do some quick back-of-the-napkin math.

If your average electric bill is **$250 a month**, over the next 10 years you will hand over **$30,000** to {{utility_company}}.

And if utility rates keep inflating at their historic average of 6-8% per year, that total jumps closer to **$42,000**.

At the end of those 10 years, how much of that $42,000 do you get back?

**$0.**

It is 100% unrecoverable utility rent.

Now consider the Solar Ownership alternative:
* **Upfront Cost**: $0 Out-of-Pocket
* **Monthly Payment**: Fixed at ~$165/mo (replaces your $250+ utility bill)
* **Equity Built**: Every single payment builds real asset equity in your property

Why continue renting power from a monopoly when you can own your power grid for less than what you're already spending today?

👉 **[See how much equity your roof can generate over the next 10 years]**

Talk soon,

{{rep_name}}  
{{company}}
```

---

### Day 3 Email: Local Case Study
* **Subject**: How {{customer_name}} in {{city}} eliminated a $380/mo electric bill
* **Preview Text**: Real numbers, real savings, and $0 upfront out-of-pocket...
* **Framework**: Social Proof & Local Case Study.

```markdown
Hey {{first_name}},

Meet {{customer_name}}, a homeowner right here in {{city}}.

Last year, their summer electric bill hit an all-time high of **$380/month**. They were running the air conditioning, trying to keep their kids comfortable, but dreading the mailbox every 30 days.

They looked into solar a few years back, but got overwhelmed by pushy salespeople and confusing quotes.

Here is what changed when we conducted a 15-minute Utility Bill Review for their home:

1. **Replaced the $380/mo utility bill** with a fixed $190/mo solar payment.
2. **Locked in a 25-Year Production Guarantee** protecting them against all future {{utility_company}} rate hikes.
3. **Built immediate home equity** without spending a single dollar out-of-pocket upfront.

Today, {{customer_name}}'s electric bill statement reads **$0** every single month.

Want to see if your roof qualifies for the exact same rate-lock program?

👉 **[Click here to schedule your 15-Minute Solar Utility Review]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 4 Email: Addressing "Is Solar a Scam?"
* **Subject**: Is solar a scam? (An honest answer from an energy consultant)
* **Preview Text**: The truth about bad contractors, hidden fees, and cheap equipment...
* **Framework**: The Paint & Contractor Reframe.

```markdown
Hey {{first_name}},

If you've spent any time on Facebook or news sites, you've probably seen horror stories about solar companies.

*"They promised $0 bills and it didn't work!"*  
*"The installation crew damaged the roof!"*

When homeowners ask me if solar is a scam, I tell them the truth: **There are definitely sloppy contractors in this industry giving everyone else a bad name.**

Think about it this way:

If a sloppy contractor paints your neighbor's house terribly and the paint starts peeling off two weeks later... does that mean *paint* is a scam? 

Or was that specific contractor just sloppy?

Solar technology isn't a scam—converting sunlight into electricity is pure physics. But working with an unvetted installer who uses sub-par equipment and over-promises production *will* leave you burned.

That is why we provide:
* Tier-1 Monocrystalline Panels (Max Efficiency)
* Enphase Microinverters & Battery Backup Systems
* 25-Year Linear Power Production Guarantees

Don't let a bad contractor stop you from protecting your family from utility rate inflation.

👉 **[Book a 15-minute transparent review—no pressure, just clear numbers]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 5 Email: Net Metering & The Rate Hike Clock
* **Subject**: The {{utility_company}} Rate Hike Clock is ticking...
* **Preview Text**: Why waiting to lock in net metering rates costs homeowners thousands...
* **Framework**: Short Time-Gap Urgency & Net Metering Locks.

```markdown
Hey {{first_name}},

In sales and home finances, there are two choices: take control before rates rise, or react after the price hike hits your bank account.

Right now, homeowners in {{state}} have access to **Net Metering Programs** that allow you to sell excess solar energy back to the grid at full retail value.

However, utility monopolies are aggressively lobbying state commissions to reduce net metering credits for future solar adopters.

Once net metering guidelines change in your utility district, grandfathered solar owners keep their 100% full-value rate lock, while late adopters get significantly lower credit returns.

Every month you wait to lock in your solar production agreement, you burn through another $250-$400 in unrecoverable utility payments while risking rate-lock expiration.

How much longer are you willing to let {{utility_company}} dictate your monthly overhead?

👉 **[Lock in your grandfathered Net Metering status in 15 minutes]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 6 Email: "Heavy Is the Head That Wears the Crown"
* **Subject**: A quick question for the head of the household...
* **Preview Text**: Who really bears the burden of your monthly household electric bill?
* **Framework**: Spousal & Partner Responsibility Reframe.

```markdown
Hey {{first_name}},

Have you ever heard the old saying: *"Heavy is the head that wears the crown"*?

The weight of the crown isn't the gold or the prestige—it is the heavy responsibility of making hard decisions to protect your family's future.

Let me ask you a direct question:

Who manages the household budget every month? Who looks at the electric bills and feels the stress when rates spike during summer peak hours?

**You do.**

So is it fair to let hesitation or fear prevent you from taking control of an overhead expense that you bear the sole responsibility for managing?

Taking control of your energy costs isn't about buying panels on a roof. It's about executing your responsibility to protect your family's financial future against compounding rate inflation.

👉 **[Take 15 minutes today to lock in a fixed, lower monthly energy rate]**

Respectfully,

{{rep_name}}  
{{company}}
```

---

### Day 7 Email: The Island vs. The Mountain
* **Subject**: The Island of Utility Fear vs. The Mountain of Power Ownership
* **Preview Text**: Perspective matters when looking at 20-year energy decisions...
* **Framework**: The Island & Mountain Analogy.

```markdown
Hey {{first_name}},

Imagine standing on a small, flat island surrounded by fog.

From that flat island, all you can see is immediate risk—the short-term effort of making a change, switching from {{utility_company}}, and setting up a solar installation.

Because the view is limited, most homeowners stay trapped on that flat island, paying high utility bills year after year because staying still feels "safe."

Now imagine hiking to the top of a high mountain.

From the top of the mountain, the fog clears, and you see the full 20-year horizon:
* **On the Flat Island**: You hand over $65,000+ in utility rent to {{utility_company}} over 20 years, gaining $0 equity.
* **On the Mountain Top**: You lock in a fixed $160/mo payment, save $35,000 in energy costs, and add $25,000 in tax-exempt equity to your home.

Which perspective are you using to make decisions for your home today? The flat island of immediate fear, or the mountain top of long-term family security?

👉 **[Click here to view your 20-Year Mountain Top Solar Breakdown]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 8 Email: Grid Independence & Storm Season
* **Subject**: What happens when the grid goes down in {{city}}?
* **Preview Text**: Protecting your family with battery backup and seamless storage...
* **Framework**: Pillar 3 - Grid Independence & Outage Backup.

```markdown
Hey {{first_name}},

When severe weather hits {{state}} and summer storms knock out local transformers, how long does your family have before the food in the fridge spoils and the AC dies?

Centralized utility grids are aging, overloaded, and increasingly unreliable.

When you install a tier-1 solar system paired with smart battery storage (like Enphase or Tesla Powerwall), your home automatically detaches from the failing grid the moment power drops.

* Your lights stay on.
* Your refrigerators stay cold.
* Your medical devices and AC units keep running seamlessly.

While your neighbors sit in the dark waiting for {{utility_company}} repair trucks, your family enjoys total energy independence.

Power ownership isn't just about saving money—it's about security when the grid fails.

👉 **[See how battery storage fits into your home's custom solar setup]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 9 Email: The 180 Summer Bills Left
* **Subject**: You only have about 180 summer electric bills left...
* **Preview Text**: The 4,000 Dots Analogy applied to your home energy timeline...
* **Framework**: The 4,000 Dots Analogy.

```markdown
Hey {{first_name}},

Scientists estimate that the average human life consists of roughly **4,000 weeks**.

If you're 40 years old today, over 2,000 of those dots are already gone. Another third will be spent sleeping. That leaves you with a finite window of time to build real freedom and eliminate wasted overhead.

If you plan on living in your home for the next 15 years, you have roughly **180 summer electric bills** ahead of you.

You have two choices for those remaining 180 bills:

1. **Option A**: Circle each month's calendar dot while mailing $300+ checks to {{utility_company}}, letting them control your budget.
2. **Option B**: Draw a line in the sand today, lock in a fixed $0-down solar payment, and keep that money in your family's bank account.

How many more summer bills are you willing to give away before you take control?

👉 **[Stop wasting remaining summer bills—book your 15-min utility review]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 10 Email: McDonald's Worker vs. Energy Entrepreneur
* **Subject**: Is staying with {{utility_company}} actually the "safe" option?
* **Preview Text**: The risk reframe that flips utility monopoly logic on its head...
* **Framework**: McDonald's Worker vs. Entrepreneur Risk Reframe.

```markdown
Hey {{first_name}},

When I speak with homeowners in {{city}}, many tell me: *"I'm just playing it safe for now by staying with the power company."*

Let's analyze what "safe" actually means.

Imagine two individuals:
* **The McDonald's Worker**: Takes the predictable, low-risk hourly path. But their income is capped forever, and they have $0 upside.
* **The Business Entrepreneur**: Takes calculated control, accepts short-term change, and builds massive long-term equity and freedom.

Staying with {{utility_company}} isn't the "safe" option—it is the McDonald's worker path of electricity. You are accepting **guaranteed 8-12% annual price inflation** while building $0 home equity.

Switching to solar ownership is the calculated entrepreneur move: you take control, lock in a fixed payment, and build equity in your own home asset.

Which energy path makes more financial sense for your home?

👉 **[Take the calculated step toward energy equity today]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 11 Email: Home Equity & Property Tax Shield
* **Subject**: Boost your home value by $20,000 (Without raising property taxes)
* **Preview Text**: How solar installations add appraisal value while shielding tax assessments...
* **Framework**: Fixed Asset Home Equity & Tax Credit Incentives.

```markdown
Hey {{first_name}},

Did you know that according to the *National Bureau of Economic Research*, residential solar installations add an average of **$20,000 in appraisal value** for every $1,000 saved in annual energy costs?

Here is the best part:

In {{state}}, energy-producing home improvements are protected under the **Renewable Energy Property Tax Exemption**. 

That means:
* Your home's market value increases immediately.
* Your local property tax assessment **does NOT increase** as a result of the solar addition.
* You qualify for the **30% Federal Investment Tax Credit (ITC)**, allowing you to deduct thousands directly off your federal tax burden.

You are transforming a volatile monthly utility expense into a tax-shielded home asset.

Want to see how much appraisal equity a custom solar array adds to your home address?

👉 **[Calculate your home equity increase in 15 minutes]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 12 Email: Usain Bolt & The Lion
* **Subject**: Why every successful homeowner needs a Usain Bolt mindset...
* **Preview Text**: The dual motivation required to make lasting home financial changes...
* **Framework**: The Usain Bolt & Lion Pre-Frame.

```markdown
Hey {{first_name}},

Have you ever heard of Usain Bolt?

He is the fastest sprinter in human history. Put him on a track with a gold medal at the finish line, and he runs fast.

Now imagine putting a hungry lion on the track chasing right behind him... **he runs twice as fast!**

The most successful homeowners we work with in {{city}} operate with the exact same dual motivation:

1. **The Pull Toward Success (The Gold Medal)**: Locked $0 power bills, $30,000+ in long-term savings, and full battery backup during blackouts.
2. **The Push Away From Consequence (The Lion)**: Refusing to let {{utility_company}} drain another $40,000 in compounding rate hikes from their retirement savings.

If you only have a weak goal, life gets busy and you put off taking action. But when you realize the utility "lion" is burning through your bank account every month, fixing your energy overhead becomes non-negotiable.

👉 **[Stop running from rate hikes—lock in your energy freedom today]**

Best,

{{rep_name}}  
{{company}}
```

---

### Day 13 Email: 3-Minute Video Breakdown
* **Subject**: 3-Minute Breakdown: How {{utility_company}} calculates summer rate hikes
* **Preview Text**: Watch this short video before your next electric bill arrives...
* **Framework**: Setter Educational Nurture Video Offer.

```markdown
Hey {{first_name}},

Most homeowners in {{city}} have no idea how their monthly electric bill is actually calculated.

They assume they are paying a flat rate per kilowatt-hour. In reality, {{utility_company}} uses complex **Tiered Rate Blocks** and **Time-of-Use (TOU) Peak Pricing** to charge you up to 300% more during summer hours.

I recorded a short **3-minute video breakdown** explaining:
* How TOU pricing spikes your bill between 4 PM and 9 PM.
* Why standard energy efficiency (LED lights, thermostat tweaks) won't stop rate tier inflation.
* How a tier-1 solar rate lock bypasses TOU price gouging entirely.

👉 **[Click here to watch the 3-minute Utility Rate Breakdown video]**

After watching, let me know if you have any questions about your roof's qualification status!

Best,

{{rep_name}}  
{{company}}
```

---

### Day 14 Email: The "I Failed You" Courtesy Apology
* **Subject**: I owe you an apology, {{first_name}}...
* **Preview Text**: My final note regarding your home's rate review in {{city}}...
* **Framework**: The Apology Pattern Interrupt & Breakup Email.

```markdown
Hey {{first_name}},

This is my final email regarding your home's utility rate review in {{city}}.

I wanted to send a quick note to sincerely apologize.

Over the past two weeks, I failed to clearly show you how continuing to pay variable utility rent to {{utility_company}} is costing your household thousands in unrecoverable energy inflation.

I know you opted in because you were frustrated with high electric bills, and it was my responsibility to help you see past short-term hesitation to protect your household budget.

I genuinely apologize for not serving you better.

If {{utility_company}} raises your rates again next summer and you decide you've finally had enough of compounding bills, our door is always open.

You can re-claim your custom solar proposal anytime right here:

👉 **[Claim your grandfathered Solar Rate Lock Review]**

I wish you and your family all the very best.

Sincerely,

{{rep_name}}  
Founder & Consultant, {{company}}
```

---

## Section 3: Implementation, Personalization Tags, & Conversion Playbook

### 1. Dynamic Personalization Tag Reference
Ensure all dynamic fields are integrated into your CRM (GoHighLevel, Close.io, HubSpot) prior to launching campaigns:

| Tag Identifier | Description | Example Replacement |
| :--- | :--- | :--- |
| `{{first_name}}` | Lead's First Name | *John* |
| `{{rep_name}}` | Assigned Setter/Closer Name | *Alex* |
| `{{company}}` | Solar Business Legal/Brand Name | *Solar Impact Energy* |
| `{{city}}` | Prospect's City | *Austin* |
| `{{state}}` | Prospect's State | *Texas* |
| `{{utility_company}}` | Local Electric Utility Provider | *Austin Energy / Oncor* |
| `{{customer_name}}` | Case Study Homeowner Name | *The Miller Family* |

### 2. A/B Split-Testing Protocol (Casual vs. Styled Format)
* **Email Format Split Test**: Split test plain text / casual Google Doc style emails against HTML templates. In B2C sales, plain text emails consistently outperform styled graphics because they bypass promotional tabs and feel like a direct, personal 1-on-1 message from a consultant.
* **Subject Line Testing**: Test direct problem statements (*"Your {{utility_company}} bill last summer"*) against curiosity loops (*"Renting vs Owning power in {{city}}"*).

### 3. Transitioning Nurtured Leads to Calendar Conversions
When a lead replies to an SMS or clicks an email CTA link:
1. **Immediate AI Response**: Trigger an automated notification to your sales rep or AI setter to reply within **60 seconds**.
2. **Qualify Usage & Roof**: Confirm monthly bill average ($150+) and roof shading status.
3. **Calendar Booking**: Direct qualified leads immediately to the closer's calendar for a **15-Minute Solar Utility Review**.

---
*Curriculum & Sequences compiled for B2C Residential Solar Sales Execution.*
