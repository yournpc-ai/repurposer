import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { ArrowLeft, Upload, Wand2, Save, Trash2, FileText } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Speaker {
  id: string
  name: string
  title: string | null
  language: string
  avatar_url: string | null
  persona: SpeakerPersona | null
  created_at: string
  updated_at: string | null
}

interface SpeakerPersona {
  core_values: string[]
  favorite_metaphors: string[]
  sentence_style: string
  emotional_tone: '理性' | '激情' | '温和' | '犀利' | '幽默'
  typical_hooks: string[]
  avoid_words: string[]
}

interface Asset {
  id: string
  type: string
  file_url: string | null
  extracted_text: string | null
  processed_at: string | null
  created_at: string
}

export const Route = createFileRoute('/speakers/$id')({
  component: SpeakerDetailPage,
})

function SpeakerDetailPage() {
  const { id } = Route.useParams()
  const navigate = useNavigate()

  const [speaker, setSpeaker] = useState<Speaker | null>(null)
  const [materials, setMaterials] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  // Editable fields
  const [name, setName] = useState('')
  const [title, setTitle] = useState('')
  const [persona, setPersona] = useState<SpeakerPersona | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const [speakerRes, materialsRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/speakers/${id}`),
        fetch(`${API_URL}/api/v1/speakers/${id}/assets`),
      ])
      if (!speakerRes.ok) throw new Error('Speaker not found')
      const speakerData = await speakerRes.json()
      const materialsData = await materialsRes.json()
      setSpeaker(speakerData)
      setMaterials(materialsData)
      setName(speakerData.name)
      setTitle(speakerData.title || '')
      setPersona(speakerData.persona)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load speaker')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [id])

  const handleUpdateSpeaker = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    setMessage('')
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, title, persona }),
      })
      if (!res.ok) throw new Error('Failed to update speaker')
      setMessage('Speaker updated')
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setSaving(false)
    }
  }

  const handleGeneratePersona = async () => {
    setGenerating(true)
    setError('')
    setMessage('')
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/persona/generate`, {
        method: 'POST',
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Generation failed')
      setPersona(data)
      setMessage('Persona generated successfully')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    setMessage('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/assets`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('Upload failed')
      setMessage('Material uploaded')
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDeleteMaterial = async (assetId: string) => {
    if (!confirm('Delete this material?')) return
    try {
      const res = await fetch(`${API_URL}/api/v1/speakers/${id}/assets/${assetId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error('Delete failed')
      setMessage('Material deleted')
      fetchData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const updatePersonaField = <K extends keyof SpeakerPersona>(
    field: K,
    value: SpeakerPersona[K]
  ) => {
    setPersona((prev) => (prev ? { ...prev, [field]: value } : null))
  }

  const updateListField = (field: keyof SpeakerPersona, value: string) => {
    updatePersonaField(field, value.split('\n').filter((s) => s.trim()))
  }

  if (loading && !speaker) {
    return <div className="p-6">Loading...</div>
  }

  if (!speaker) {
    return <div className="p-6 text-red-600">{error || 'Speaker not found'}</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link
          to="/speakers"
          className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="text-2xl font-bold">{speaker.name}</h1>
      </div>

      {(message || error) && (
        <div
          className={`p-4 rounded-lg ${
            error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
          }`}
        >
          {error || message}
        </div>
      )}

      <form onSubmit={handleUpdateSpeaker} className="bg-white p-6 rounded-lg shadow-sm border space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
            />
          </div>
        </div>

        <div className="border-t pt-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Style Persona</h2>
            <button
              type="button"
              onClick={handleGeneratePersona}
              disabled={generating || materials.length === 0}
              className="inline-flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded-md hover:bg-purple-700 disabled:opacity-50"
            >
              <Wand2 className="w-4 h-4" />
              {generating ? 'Generating...' : 'Generate from Materials'}
            </button>
          </div>

          {persona ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Emotional Tone</label>
                <select
                  value={persona.emotional_tone}
                  onChange={(e) => updatePersonaField('emotional_tone', e.target.value as SpeakerPersona['emotional_tone'])}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                >
                  <option value="理性">理性</option>
                  <option value="激情">激情</option>
                  <option value="温和">温和</option>
                  <option value="犀利">犀利</option>
                  <option value="幽默">幽默</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Sentence Style</label>
                <input
                  type="text"
                  value={persona.sentence_style}
                  onChange={(e) => updatePersonaField('sentence_style', e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Core Values (one per line)</label>
                <textarea
                  value={persona.core_values.join('\n')}
                  onChange={(e) => updateListField('core_values', e.target.value)}
                  rows={4}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Favorite Metaphors (one per line)</label>
                <textarea
                  value={persona.favorite_metaphors.join('\n')}
                  onChange={(e) => updateListField('favorite_metaphors', e.target.value)}
                  rows={3}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Typical Hooks (one per line)</label>
                <textarea
                  value={persona.typical_hooks.join('\n')}
                  onChange={(e) => updateListField('typical_hooks', e.target.value)}
                  rows={4}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Avoid Words (one per line)</label>
                <textarea
                  value={persona.avoid_words.join('\n')}
                  onChange={(e) => updateListField('avoid_words', e.target.value)}
                  rows={3}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
                />
              </div>
            </div>
          ) : (
            <div className="text-gray-500 bg-gray-50 p-6 rounded-lg text-center">
              No persona yet. Upload materials and click Generate.
            </div>
          )}
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>

      <div className="bg-white p-6 rounded-lg shadow-sm border space-y-4">
        <h2 className="text-lg font-semibold">Past Materials</h2>

        <div className="flex items-center gap-4">
          <label className="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-md cursor-pointer transition-colors">
            <Upload className="w-4 h-4" />
            {uploading ? 'Uploading...' : 'Upload Material'}
            <input
              type="file"
              onChange={handleFileUpload}
              disabled={uploading}
              accept=".txt,.md,.pdf,.docx,.doc"
              className="hidden"
            />
          </label>
          <span className="text-sm text-gray-500">Supports .txt, .md, .pdf</span>
        </div>

        {materials.length === 0 ? (
          <div className="text-gray-500 text-center py-8">No materials uploaded yet.</div>
        ) : (
          <div className="divide-y">
            {materials.map((asset) => (
              <div key={asset.id} className="py-4 flex items-start justify-between gap-4">
                <div className="flex items-start gap-3 min-w-0">
                  <FileText className="w-5 h-5 text-gray-400 mt-0.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">
                      {asset.file_url?.split('/').pop() || 'Untitled'}
                    </p>
                    <p className="text-sm text-gray-500">
                      {asset.extracted_text
                        ? `${asset.extracted_text.length.toLocaleString()} chars extracted`
                        : 'No text extracted'}
                    </p>
                    <p className="text-xs text-gray-400">
                      Uploaded {new Date(asset.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => handleDeleteMaterial(asset.id)}
                  className="text-red-600 hover:text-red-800 p-1"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
