import { createFileRoute, Link } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Speaker {
  id: string
  name: string
  title: string | null
  language: string
  created_at: string
}

export const Route = createFileRoute('/speakers')({
  component: SpeakersPage,
})

function SpeakersPage() {
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [name, setName] = useState('')
  const [title, setTitle] = useState('')
  const [loading, setLoading] = useState(false)

  const fetchSpeakers = async () => {
    const res = await fetch(`${API_URL}/api/v1/speakers`)
    const data = await res.json()
    setSpeakers(data)
  }

  useEffect(() => {
    fetchSpeakers()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    await fetch(`${API_URL}/api/v1/speakers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, title, language: 'zh' }),
    })
    setName('')
    setTitle('')
    setLoading(false)
    fetchSpeakers()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Speakers</h1>

      <form onSubmit={handleSubmit} className="bg-white p-4 rounded-lg shadow-sm border space-y-4 max-w-md">
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
        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Creating...' : 'Create Speaker'}
        </button>
      </form>

      <div className="bg-white rounded-lg shadow-sm border">
        <table className="min-w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Name</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Title</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Language</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Created</th>
            </tr>
          </thead>
          <tbody>
            {speakers.map((speaker) => (
              <tr key={speaker.id} className="border-t hover:bg-gray-50">
                <td className="px-4 py-2">
                  <Link
                    to={`/speakers/${speaker.id}`}
                    className="font-medium text-blue-600 hover:text-blue-800"
                  >
                    {speaker.name}
                  </Link>
                </td>
                <td className="px-4 py-2">{speaker.title || '-'}</td>
                <td className="px-4 py-2">{speaker.language}</td>
                <td className="px-4 py-2 text-sm text-gray-500">
                  {new Date(speaker.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
