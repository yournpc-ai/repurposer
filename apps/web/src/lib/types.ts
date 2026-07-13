export type MessageRole = "user" | "assistant" | "system"

export type MessageStatus = "pending" | "running" | "completed" | "failed"

export interface ChatAttachment {
  id: string
  name: string
  type: "file" | "image" | "video" | "audio"
  url?: string
  size?: number
  status: "uploading" | "uploaded" | "failed"
}

export interface ChatMarker {
  id: string
  type: "status" | "tool" | "separator" | "error"
  label: string
  timestamp?: string
  meta?: Record<string, unknown>
}

export interface ChatMessageMeta {
  status?: MessageStatus
  progress?: number
  currentStep?: string
  markers?: ChatMarker[]
  results?: {
    clip_ids?: string[]
    derivative_ids?: string[]
  }
  error?: string
  params?: Record<string, unknown>
}

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  attachments: ChatAttachment[]
  meta: ChatMessageMeta
  parentMessageId?: string
  createdAt: string
  updatedAt?: string
}

export interface ChatThread {
  projectId: string | null
  title: string
  messages: ChatMessage[]
  isGenerating: boolean
  error: string | null
}

export type Tone =
  | "professional"
  | "thoughtLeadership"
  | "conversational"
  | "academic"

export interface Project {
  id: string
  title: string
  status: string
  speaker_id: string | null
  event_name: string | null
  language: string
  created_at: string
}

export interface Speaker {
  id: string
  name: string
  title?: string | null
  persona?: {
    emotional_tone?: string
    sentence_style?: string
  } | null
}

export interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  transcript: string | null
  processing_status: string
  processing_error: string | null
  created_at: string
}

export interface Clip {
  id: string
  project_id: string
  hook: string
  title_options: string[]
  music_mood: string
  status: string
  video_url: string | null
  render_spec: unknown | null
  render_status: string | null
  render_error: string | null
  duration: number
  created_at: string
  updated_at: string | null
}

export interface Derivative {
  id: string
  project_id: string
  type: string
  content: {
    content?: string
    hashtags?: string[]
    quotes?: { quote: string; attribution: string }[]
    slides?: { title: string; body?: string }[]
    tldr?: string
    key_points?: string[]
    full?: string
    title?: string
  }
  language: string
  image_url: string | null
  created_at: string
  updated_at: string | null
}

export interface Job {
  id: string
  status: string
  current_step: string | null
  progress: number
  error: string | null
}

export interface BrandTemplate {
  id: string
  name: string
  config: {
    captionColor?: string
    logoUrl?: string
    cta?: string
  }
}
