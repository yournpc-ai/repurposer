
## L1 read the named film

**user**: There's a film in this project. Read its current state and tell me: what storyboard version is it on, how many scenes does it have, and what aspect ratio is it?

**assistant**: Here's the current state:

- **Storyboard version:** 1
- **Scenes:** 15 (s1–s15)
- **Aspect ratio:** 9:16 (vertical)

Total runtime lands around 89 seconds, voiceover is on, and the music mood is unset.

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed')]


## L2 overlay vs screenshot text

**user**: Two different things, please: (1) the film's OPENING scene animates a few word lines — quote them exactly; (2) in the captured fold view of the homepage, what is the big heading actually visible at the top of the page?

**assistant**: Here's both.

**(1) The opening scene (s1)** is a dark "words" card, 3 seconds, no narration. It animates three lines in sequence:

- **"Slide deck blues?"**
- **"Same old slides."**
- **"Almost there."**

**(2) The big heading in the captured fold view** of the homepage reads:

> **We enable developers to create stunning presentations**

with **"stunning presentations"** picked out in blue and the first part in dark grey. That matches element `s0e11` on the page, which is the line the film's s2 hero scene also carries as its subtitle.

One thing worth knowing if you want to move on: the film's music mood is currently set to **none**, so it renders with voiceover only.

Want me to add a music bed, or look at another scene?

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed')]


## L3 scoped view read

**user**: Look closely at the homepage's second captured view (page 0, shot 1 — the 'Create next-level presentations' section). What's on the LEFT side of that section, and what does the little card below the 'Learn more' link say?

**assistant**: Looking at page 0, shot 1:

**Left side:** a large green rounded panel holding a mock code editor card (a dark browser-style window titled "smoosh.py" with a few lines of Python and a big white play button over it). Above it, a handwritten-style note with an arrow pointing down into the editor says **"feel free to copy some code 😜"**. A dashed blue connector trails off the bottom of the panel.

**The card below "Learn more":** a light purple-bordered box starting with a bulb emoji, reading **"Share interactive slides so your viewers can easily copy code snippets and interact with links."** ("Share interactive slides" is bolded.)

Both of those are elements the scene can name if you want the camera to land on them: the green code panel is image element s1e16, and the card is the text element s1e15. Want me to change scene s5's push target from "Learn more" to one of them?

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed')]


## L4 framing edit with real element id

**user**: Scene 5 walks the 'Create next-level presentations' view and its camera pushes to the 'Learn more' button. Change that scene's camera focus to the 'Share interactive slides' card instead.

**assistant**: Done — the change is applied to the storyboard.

**Scene 5** ("Create next-level presentations" view): the camera push at the 2-second mark now lands on the **"Share interactive slides"** card — the light-bordered note under the Learn more link — instead of the Learn more button. Everything else about the scene is untouched: same view, 8 seconds, same narration.

Totals stay at **15 scenes · 89s**.

Want me to start making the film with this version?

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed'), ('draft', 'chat.activity.storyboardEdit', 'active'), ('draft', 'chat.activity.storyboardEditDone', 'completed')]

L4 pending version=2 scene5 focuses=['s1e15']


## L6 authored vs actual duration

**user**: How long does scene 14 actually play in the delivered film? I mean the real rendered duration, not the design figure.

**assistant**: In the rendered cut, **scene 14 plays for 8.2 seconds** (245 frames at the project's frame rate), about 0.2 seconds longer than the 8-second authored figure.

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed')]


## L5 budget breach re-scopes

**user**: Pull up every captured view of the site so you can see them all, then tell me what the pricing page's fold shows.

**assistant**: All 14 captured views are in. Here's the whole set, then the pricing fold.

| Page | Views | What it covers |
| --- | --- | --- |
| 0 · snappify home | 6 shots | Hero with the "Video Exports" badge and a code-window visual, "Create next-level presentations", User Stories, "Your branding will be on point", "Manage your code snippets in one place", closing CTA + footer |
| 1 · Pricing | 4 shots | The fold, a scrolled view starting at the plan cards, User Stories, closing CTA + footer |
| 2 · Video Export | 2 shots | "Get ready to create stunning videos" with the download buttons, then the Discord block and footer |
| 3 · Video Export (duplicate capture) | 2 shots | Same two states as page 2, same content |

The pricing page's fold (page 1, first view) shows, top to bottom:

- **The nav bar**: snappify logo, Pricing / Use Cases / Product / Resources, then Dashboard, Editor and an account icon on the right.
- **A two-tone headline**: "Your code deserves an incredible presentation", with the second half in the blue-to-pink gradient.
- **One line of copy**: "Pick the plan which fits your needs and join 40,000+ users who already create stunning presentations with snappify."
- **A promo strip**: "New! - Get up to 14 days of free access to the snappify PRO Plan with our new Challenge 🏆".
- **Four plan cards**: Free at **$0** with a Login button, Starter at **$5/month**, Professional at **$9/month** (the one highlighted with a purple border), Team at **$32/month**. Below each price is the yearly billing note ($0, $60, $108, $384), and a Monthly / Yearly toggle with "Save 33%" sits on the left.
- **The top of the comparison table** starts right at the fold: a "Dashboard" row with image upload limits (-, 100 MB, 1 GB, 5 GB).
- **Two floating widgets** in the corners: a chat bubble bottom-left, and a Discord join bar plus a "Product of the Day" badge bottom-right.

Worth knowing: none of the four pricing views are used by any scene in the film. The pricing numbers in the cut (scene 6) come from a text plate, and scene 14's "Plans from zero to thirty-two a month" walks the home page's closing CTA instead. If you want, I can point a scene at the real pricing fold so the plans are read off the page itself rather than a card.

activity frames: [('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed'), ('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed'), ('read', 'chat.inspecting.outputSpec', 'active'), ('read', 'chat.inspectingDone.outputSpec', 'completed')]

L5 read-frame count=6
