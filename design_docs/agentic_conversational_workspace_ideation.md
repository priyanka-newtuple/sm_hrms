# Ideation: The Conversational Agentic Workspace

## 🌟 The Vision: "Sidecar Intelligence"

Moving beyond a simple command bar, we envision a **Split-Panel Conversational Workspace**. The left side is the "Brain" (The Agent), and the right side is the "Body" (The UI/Data). They are perfectly synchronized in a continuous loop of conversation and action.

---

## 📐 Layout: The "Sidecar" Sidebar (Collapsible)

To solve the "crowded" feeling, we move from a fixed panel to a **Collapsible Sidecar**.

- **The Toggle**: A vertical tab or floating button (with a subtle sparkle/glow) that stays at the edge of the screen.
- **Behavior**: Clicking it slides the chat panel in/out. When it slides in, the right-side UI (the canvas) intelligently shrinks or shifts to maintain focus.
- **State**: The system remembers if you had it open or closed across page navigations.

---

## 🏛️ Persistence & History: The "Thread" Model

Conversations aren't just one-off sessions; they are **Persistent Threads**.

1. **History View**: A "History" tab within the sidebar allows you to see previous conversations, categorized by date or entity (e.g., "Chat about Senior Engineer Role").
2. **Jump-Back**: Clicking an old message "rewinds" the right-side UI to the state it was in during that conversation (if possible) or at least focuses the relevant entities.

---

## 🧠 Solving "Context Loss": The Context Navigator

To prevent the "losing details in the middle" problem common in long chats, we introduce **Context Pins** and a **Current Context Header**.

- **Context Header**: The top of the chat sidebar always shows a "Pinned Context" area. 
    - *Example*: `Discussing: [Job: Senior Dev] | [Candidate: Jane Smith]`
- **Auto-Summarization**: When a conversation passes 10 messages, the agent automatically "compresses" the early part into a short summary bubble, keeping only the actionable outcomes visible.
- **Knowledge Base Integration**: Key decisions made in the chat (e.g., "Jane is a good fit because of X") are automatically extracted and added to the **Entity Notes** on the right side, so the context is saved permanently in the database, not just the chat scroll.

---

## 👥 Collaboration & Roles: Shared vs. Private Intelligence

### 1. Role-Based Capabilities
- The Agent **inherits the user's permissions**. A 'Viewer' cannot ask the agent to "Reject this candidate," as the agent will respond: *"I'm sorry, you don't have permission to perform transitions. I can, however, summarize their resume for you."*
- **Tool Level Security**: Backend already has `require_recruiter_or_admin` decorators; the agent's tools will naturally fail and report "Access Denied" if the user is unauthorized.

### 2. The Collaboration Models
- **Private Mode (Default)**: Most chats are private to the user—a personal assistant for their daily tasks.
- **Shared Threads**: Users can "Share" a chat thread with a colleague. *"Hey @dhiraj, look at what the agent and I found regarding this candidate."*
- **The Global Timeline**: Every action an agent performs (after user approval) is posted to the **Shared Activity Feed**. This ensures everyone sees what happened, even if they weren't in the private chat.

---

## 🔄 Core Interaction Patterns

### 1. **The "Propose & Approve" Loop**
- **Agent**: "I noticed 5 candidates in Screening haven't been touched in 3 days. I've analyzed their resumes, and 3 look like a perfect fit. Should I move them to the Interview stage?"
- **UI (Right)**: The 3 candidates are highlighted with a subtle blue glow.
- **User**: "Yes, do it." (or clicks a "Move All" button inside the chat message).
- **UI (Right)**: The cards animate smoothly to the next column.

### 2. **"Drag-to-Analyze"**
- **Action**: User drags a candidate card from the right-side board and "drops" it into the chat on the left.
- **Agent**: "Analyzing John Doe... I see he has 8 years of Experience in Java. However, his salary expectations are 20% above the job range. Should I flag this for the Hiring Manager?"

### 3. **"Look at This" (Agent Pointer)**
- **Action**: Agent needs user attention on a specific data point.
- **Agent**: "Check out this candidate's recent certification in Cloud Security."
- **UI (Right)**: The screen auto-scrolls to the candidate, opens their profile, and highlights the 'Certifications' section with a pulse effect.

### 4. **"Contextual Interjection"**
- **Action**: User is manually editing a job description on the right.
- **Agent (Left)**: "I see you're updating the Job Requirements. Based on current market data for 'Senior Frontend Engineer', adding 'Tailwind CSS' as a required skill might increase qualified applicants by 15%. Want me to draft a sentence for that?"

---

## 🎨 Visual & UI Design: "The Premium Intelligence"

To achieve a **premium, minimalist, and smart** look that avoids AI cliches (no robots, magic wands, or over-the-top glows), we follow these design pillars:

### 1. **The "Glass Sidecar" (The Sidebar)**
- **Material**: Instead of a solid white/gray panel, use a **highly-refined glassmorphism** effect (`backdrop-blur-xl` with a `white/70` tint). This makes the sidebar feel like a lightweight layer floating over the data.
- **Border**: A single-pixel, semi-transparent border (`border-white/20`) that catches the "light" as you scroll.
- **Shadow**: A very soft, long shadow (`shadow-2xl` with low opacity) to give depth without bulk.

### 2. **Subtle "Intelligence" Motion**
- **The "Thought" Indicator**: Avoid the spinning loader. When the agent is processing, use a **"Breathing Dot"**—a single, elegant 4px dot that subtly pulses in opacity.
- **Text Shimmer**: When the agent is "typing" or generating a complex analysis, the text has a very faint, slow shimmer effect that moves from left to right, implying active creation rather than just fetching data.
- **Sleight-of-Hand Transitions**: When the agent proposes a change (like moving a candidate), the UI on the right doesn't just "jump." It performs a **coordinated micro-animation**—the card slightly lifts, a shadow appears where it will land, and the transition feels purposeful.

### 3. **Non-Cliche Iconography**
- **Avoid**: Sparkles (✨), Robots (🤖), Magic Wands (🪄).
- **Use**: Geometric precision. A simple, perfectly weighted **"Level" icon** or a **"Nodal" dot** (representing connection and intelligence).
- **Tool Feedback**: When a tool is called, show a minimalist "System Terminal" chip—monospaced font, 10px size, tucked away in the message corner. It implies professional-grade power under the hood.

### 4. **Adaptive Layout (The "Breath" Effect)**
- **Responsive Canvas**: When the sidebar opens, the right-side UI doesn't just get squished. It **re-layouts elegantly**. For example, the Pipeline Board might switch from 7 columns to a "Focused 3 Column" view, hiding terminal stages automatically to give you room to "think" with the agent.
- **Contextual Highlighting**: Instead of bright yellow highlights, use **Depth-of-Field**. When the agent points to a candidate, the rest of the board subtly desaturates or blurs slightly (`blur-[1px]`), bringing the focus candidate into sharp, crisp relief.

### 5. **Premium Typography**
- **Weights**: Use `Inter` but lean heavily on `Light (300)` and `Medium (500)` weights. Avoid bold headers; use all-caps with increased letter spacing for a "Swiss-design" professional look.
- **Contrast**: High contrast for text, but low contrast for UI containers. Let the information be the hero, not the boxes.

---

## 🏗️ Technical Architecture Concepts

### 1. **`AgentUIContext`**
A shared state that tracks:
- `activeContext`: What is currently visible/selected on the right.
- `pendingChanges`: Actions proposed by the agent but not yet committed.
- `agentFocus`: Which specific element the agent is currently "pointing" to.

### 2. **`AgentMessageBus`**
A simple event system where:
- The UI emits events like `USER_CLICKED_CANDIDATE(id: "123")`.
- The Agent subscribes and responds with `AGENT_WANTS_TO_HIGHLIGHT(path: "candidate.skills")`.

### 3. **Tool-Integrated Chat**
The backend `document_agent.py` and `executor.py` results are streamed to the chat. Each tool call is rendered as a "Thought Block" in the conversation, allowing the user to inspect the raw tool input/output if they want to.

---

## 🧭 Discovery: Helping Users Start

To ensure new users aren't staring at a blank chat box, we incorporate **Capability Discovery** directly into the sidecar.

- **"Quick Start" Chips**: When the sidecar is opened for the first time or in a new context, it displays 3-4 subtle chips representing common agentic actions:
    - `[📄 Screen New Resumes]`
    - `[🔍 Find Top Matches]`
    - `[🔄 Cleanup Stale Apps]`
- **The "Command Library"**: A small icon in the chat input opens a minimalist overlay showing all the "Tools" the agent currently has access to (extracted from the backend Tool Manifest), explained in human terms.
- **Contextual Welcome**: Instead of "Hello," the agent starts with context: *"I see you're looking at the Engineering Pipeline. I can help you summarize the top 5 candidates or check for any SLA risks. What should we do first?"*

---

## 🗺️ Roadmap: The Path to Autonomy

1. **Phase 1: Human-in-the-Loop (Current focus)**
   - Agent proposes -> User clicks "Approve" -> Action happens.
   - Zero autonomy. No surprises.

2. **Phase 2: "Delegate & Notify"**
   - User gives a bounded task: *"Screen all new applicants today and move the top 3 to 'Shortlisted'. Just let me know when you're done."*
   - Agent performs actions and sends a summary notification.

3. **Phase 3: "Agentic Rules"**
   - User sets permanent instructions: *"Whenever a candidate from Google applies for a Backend role, automatically move them to screening and flag me."*

---

## 🚀 Updated Phase 1 MVP Idea: "The Intelligence Sidecar"

1. **Collapsible Sidebar**: A clean, sliding chat panel on the left.
2. **Context Pinning**: A header that tracks what entities the conversation is focused on.
3. **History Tab**: Simple listing of recent threads.
4. **Approval Bubbles**: Chat messages with "Execute" buttons for the existing transition API.
