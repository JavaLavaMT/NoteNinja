from datetime import datetime


def generate(transcript, meeting_name, client):
    print("  Generating notes with Claude...")

    date_str = datetime.now().strftime("%B %d, %Y")

    has_speakers = any(
        line.startswith("Speaker ") for line in transcript.splitlines()[:20]
    )
    speaker_note = (
        "\nThe transcript includes speaker labels (Speaker A:, Speaker B:, etc.). "
        "Attribute action items and decisions to specific speakers. "
        "List attendees as 'Speaker A', 'Speaker B', etc. unless real names are mentioned."
        if has_speakers else ""
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": f"""Convert this meeting transcript into clean, structured meeting notes.

Meeting: {meeting_name}
Date: {date_str}{speaker_note}

Be exhaustive with action items — capture EVERY commitment, task, follow-up, or "we should X" no matter how casually mentioned. Always include specific times, dates, or deadlines when stated. Do not summarize away specifics.

Transcript:
{transcript}

---

Format as markdown using exactly this structure:

# {meeting_name}
**Date:** {date_str}

## Attendees
[names or speaker labels, or "Not identified"]

## Key Discussion Points
[bullet points]

## Decisions Made
[bullet points, or "None noted"]

## Action Items
- [ ] [task] — [owner/speaker if known] — [due date/time if mentioned]

## Summary
[2-3 sentences]""",
            }
        ],
    )

    return message.content[0].text
