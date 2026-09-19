# Appointment Reminder & Attendance Maximizer System
### *Multi-Channel Automated Sequence (SMS, Email, Voice AI) Based on sequence2.png*

---

## Executive Overview & Attendance Architecture

Maximizing show-up rates for scheduled sales calls requires a synchronized, multi-channel approach. When prospects book an appointment, life and daily fires cause attendance rates to drop if follow-ups rely on generic automated calendar invites.

This reminder system is modeled directly on the multi-channel workflow in `sequence2.png`. It deploys three synchronized communication tracks to achieve 85%+ show rates:
1. **AI SMS Agent Sequence (5 Touchpoints)**: Immediate confirmation, 24-hour, 6-hour, 1-hour, and 10-minute SMS reminders built with pattern-interrupt accountability questions and low-friction access links.
2. **Email Sequence (3 Touchpoints)**: Immediate confirmation with calendar invite, 24-hour prep email, and 1-hour access email.
3. **AI Call Agent / Voice AI Sequence (2 Touchpoints)**: Conversational 6-hour and 1-hour automated phone check-ins to lock in attendance.

All touchpoints support both **Virtual Meetings** (Google Meet, Zoom) and **In-Person Meetings** (home address).

---

## Section 1: AI SMS Agent Sequence

### Sequence Strategy & Tonality Guidelines
* **Pattern-Interrupt Accountability**: Asking direct questions like *"Can I count on you to actually show up?"* filters out low-intent leads early and dramatically increases commitment.
* **Low-Friction Access**: Every reminder includes a direct one-click meeting link or home address.
* **Casual, Professional Tone**: Avoid corporate fluff. Speak like a peer who values both their own time and the prospect's time.

---

### Touchpoint 1: Immediate Confirmation SMS (0 Minutes Post-Booking)
* **Timing**: Sent immediately upon booking.
* **Objective**: Establish personal connection, confirm time/link, and lock in verbal commitment.

#### Virtual Meeting Option (Google Meet / Zoom)
```text
Hey {{lead_first_name}} it's {{rep_name}} with {{company_name}}

I'll meet with you at {{appointment_date_time}} using this link-

{{meeting_link}}

Can I count on you to actually show up?
```

#### In-Person Meeting Option (Home Address)
```text
Hey {{lead_first_name}} it's {{rep_name}} with {{company_name}}

I'll meet with you at {{appointment_date_time}} at your home address-

{{prospect_home_address}}

Can I count on you to actually show up?
```

#### Production Template Example - Virtual Meeting (Voltaik AI)
```text
Hey Mohamed it's Mohamed with voltaik AI

I'll meet with you at Thursday, September 17, 2026 9:00 PM using this link-

https://meet.google.com/zok-rdmz-zhp

Can I count on you to actually show up?
```

#### Production Template Example - In-Person Meeting at Home Address (Voltaik AI)
```text
Hey Mohamed it's Mohamed with voltaik AI

I'll meet with you at Thursday, September 17, 2026 9:00 PM at your home address-

123 Solar Way, Austin, TX 78701

Can I count on you to actually show up?
```

---

### Touchpoint 2: 24-Hour Reminder SMS
* **Timing**: 24 hours before appointment.
* **Objective**: Re-confirm attendance and outline meeting agenda.

#### Virtual Meeting Option
```text
Hey {{lead_first_name}}, quick check-in for our call tomorrow at {{appointment_time}}. 

We'll be going over your energy usage and rate lock structure on Google Meet: {{meeting_link}}

Are we still good for tomorrow?
```

#### In-Person Meeting Option
```text
Hey {{lead_first_name}}, quick check-in for our meeting tomorrow at {{appointment_time}}. 

We'll be meeting at your home address here: {{prospect_home_address}}

Are we still good for tomorrow?
```

---

### Touchpoint 3: 6-Hour Reminder SMS
* **Timing**: 6 hours before appointment.
* **Objective**: Value prep check (soft homework / video review).

#### Virtual Meeting Option
```text
Hey {{lead_first_name}}! Looking forward to our call at {{appointment_time}} today. 

Before we hop on, take 2 mins to check out this quick breakdown so you know exactly what to expect: {{prep_link}}

Here is the meeting room link for later: {{meeting_link}}
```

#### In-Person Meeting Option
```text
Hey {{lead_first_name}}! Looking forward to seeing you at {{appointment_time}} today. 

Before our in-home visit at {{appointment_time}}, take 2 mins to review this quick overview: {{prep_link}}

Meeting location: {{prospect_home_address}}
```

---

### Touchpoint 4: 1-Hour Reminder SMS
* **Timing**: 1 hour before appointment.
* **Objective**: Final calendar lock and computer / travel readiness check.

#### Virtual Meeting Option
```text
Hey {{lead_first_name}}, we're on in 60 mins at {{appointment_time}}. 

Make sure you're in a quiet spot with your computer ready. Here's your link: {{meeting_link}}

See you shortly!
```

#### In-Person Meeting Option
```text
Hey {{lead_first_name}}, we're meeting in 60 mins at {{appointment_time}}. 

Here is the Home address: {{prospect_home_address}}

See you shortly!
```

---

### Touchpoint 5: 10-Minute Reminder SMS
* **Timing**: 10 minutes before appointment.
* **Objective**: Room opening notification & immediate action.

#### Virtual Meeting Option
```text
Hey {{lead_first_name}}, I'm opening up the meeting room now. 

Hop in whenever you're ready: {{meeting_link}}
```

#### In-Person Meeting Option
```text
Hey {{lead_first_name}}, I'm set up in the conference room and ready for you. 

Let me know when you pull up! Directions: {{prospect_home_address}}
```

---

## Section 2: Automated Email Sequence

### Touchpoint 1: Immediate Confirmation Email (Right After Booking)
* **Subject**: Confirmed: Meeting on {{appointment_date_time}} with {{rep_name}}
* **Preview Text**: Important details and access link for our upcoming consultation...

#### Email Body
```markdown
Hey {{lead_first_name}},

Your consultation is officially confirmed for **{{appointment_date_time}}**.

### Meeting Access Details
* **Meeting Host**: {{rep_name}} ({{company_name}})
* **Access Link / Location**: {{meeting_link_or_home_address}}
* **Calendar Event**: A calendar invite has been sent to your email address—please click "Accept" to lock it into your schedule.

### What We Will Cover
1. Review your current overhead and operational bottleneck.
2. Map out a custom plan built specifically for your setup.
3. Compare potential savings vs. staying with your current process.

To get the absolute most out of our time together, please be at a computer or quiet space where you can view our shared screen.

If anything urgent comes up and you need to adjust your time, please let me know at least 24 hours in advance.

Looking forward to speaking with you!

Best,

{{rep_name}}  
{{company_name}}
```

---

### Touchpoint 2: 24-Hour Reminder Email
* **Subject**: Tomorrow at {{appointment_time}}: Meeting with {{rep_name}}
* **Preview Text**: Quick reminder and agenda for our scheduled call tomorrow...

#### Email Body
```markdown
Hey {{lead_first_name}},

This is a quick reminder that we are meeting tomorrow at **{{appointment_time}}**.

### Access Link / Address
👉 **{{meeting_link_or_home_address}}**

### Quick Meeting Checklist
* **Quiet Environment**: Please ensure you are in a quiet space without driving or walking.
* **Decision Makers**: If you make financial decisions with a business partner or spouse, please have them join the call.

If you have any quick questions before tomorrow, simply reply directly to this email.

See you tomorrow at {{appointment_time}}!

Best,

{{rep_name}}  
{{company_name}}
```

---

### Touchpoint 3: 1-Hour Reminder Email
* **Subject**: [Starting in 60 Minutes] Access link for {{appointment_time}}
* **Preview Text**: We start in one hour. Here is your direct meeting link...

#### Email Body
```markdown
Hey {{lead_first_name}},

We are starting our consultation in **60 minutes** at {{appointment_time}}.

Here is your direct access link:

👉 **{{meeting_link_or_home_address}}**

Please make sure your audio and video are working properly before hopping on.

See you in an hour!

Best,

{{rep_name}}  
{{company_name}}
```

---

## Section 3: AI Call Agent (Voice AI) Scripts

### Touchpoint 1: 6-Hour Reminder Call Script
* **Trigger**: 6 hours before appointment.
* **Caller ID**: {{company_phone_number}}
* **Objective**: Conversational voice verification.

```text
Voice AI: "Hey {{lead_first_name}}, this is the automated assistant for {{rep_name}} at {{company_name}}. I'm just calling to confirm our scheduled consultation today at {{appointment_time}}. Are you still all set for that time?"

[Prospect Responds: "Yes" / "Yeah, I'll be there"]

Voice AI: "Awesome! {{rep_name}} sent over the meeting link via text message. We'll see you at {{appointment_time}}. Have a great rest of your day!"

[Prospect Responds: "No" / "I need to move it"]

Voice AI: "No problem at all. I'll text you a quick rescheduling link right now so you can pick a time that works better for you. Have a great day!"
```

---

### Touchpoint 2: 1-Hour Reminder Call Script
* **Trigger**: 1 hour before appointment.
* **Caller ID**: {{company_phone_number}}
* **Objective**: Final 15-second verbal check.

```text
Voice AI: "Hey {{lead_first_name}}, quick 15-second call from {{company_name}}! We have our consultation starting in one hour at {{appointment_time}}. {{rep_name}} just texted you the meeting link. Make sure you're at your computer, and we'll see you shortly!"
```

---

## Section 4: AI Reply Handling & Edge Case Decision Trees

### Scenario 1: Prospect Replies "Can we reschedule?"
```text
AI Response: "No stress at all {{lead_first_name}}! Here is my direct scheduling calendar link so you can pick a time that works better for you: {{reschedule_link}}"
```

### Scenario 2: Prospect Replies "Who is this?"
```text
AI Response: "Hey {{lead_first_name}}, it's {{rep_name}} with {{company_name}}! You booked a consultation on our calendar for {{appointment_date_time}}. Here's the access link for our meeting: {{meeting_link_or_home_address}}"
```

### Scenario 3: Prospect No-Shows (5 Minutes Late)
```text
SMS Trigger (Sent 5 Mins Post-Start): "Hey {{lead_first_name}}, I'm in the meeting room right now. Are you having trouble with the link? Here it is again: {{meeting_link}}"
```

---

## Dynamic CRM Tag Reference

| Variable Tag | Description | Example Value |
| :--- | :--- | :--- |
| `{{lead_first_name}}` | Prospect's First Name | *Mohamed* |
| `{{rep_name}}` | Assigned Sales Rep Name | *Mohamed* |
| `{{company_name}}` | Business Legal / Brand Name | *voltaik AI* |
| `{{appointment_date_time}}` | Full Date & Time String | *Thursday, September 17, 2026 9:00 PM* |
| `{{appointment_time}}` | Time String Only | *9:00 PM* |
| `{{meeting_link}}` | Virtual Meeting URL | *https://meet.google.com/zok-rdmz-zhp* |
| `{{prospect_home_address}}` | Prospect's Home Address | *https://maps.google.com/?q=...* |
| `{{meeting_link_or_home_address}}` | Dynamic Virtual/In-Person Field | *https://meet.google.com/zok-rdmz-zhp* |
| `{{prep_link}}` | Case Study or Demo Video Link | *https://voltaik.ai/demo* |
| `{{reschedule_link}}` | Calendar Re-booking Link | *https://voltaik.ai/book* |

---
*System compiled and structured for Voltaik AI / High-Ticket B2B & Residential Sales Execution.*
