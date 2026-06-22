import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Project {
  id: string
  title: string
  event_name: string | null
  status: string
  created_at: string
}

interface Speaker {
  id: string
  name: string
}

export const Route = createFileRoute('/projects')({
  component: ProjectsPage,
})

function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [speakers, setSpeakers] = useState<Speaker[]>([])
  const [title, setTitle] = useState('')
  const [eventName, setEventName] = useState('')
  const [speakerId, setSpeakerId] = useState('')
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    const [projectsRes, speakersRes] = await Promise.all([
      fetch(`${API_URL}/api/v1/projects`),
      fetch(`${API_URL}/api/v1/speakers`),
    ])
    setProjects(await projectsRes.json())
    setSpeakers(await speakersRes.json())
  }

  useEffect(() => {
    fetchData()
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!speakerId) return
    setLoading(true)
    await fetch(`${API_URL}/api/v1/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, event_name: eventName, language: 'zh', speaker_id: speakerId }),
    })
    setTitle('')
    setEventName('')
    setSpeakerId('')
    setLoading(false)
    fetchData()
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Projects</h1>

      <form onSubmit={handleSubmit} className="bg-white p-4 rounded-lg shadow-sm border space-y-4 max-w-md">
        <div>
          <label className="block text-sm font-medium text-gray-700">Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Event Name</label>
          <input
            type="text"
            value={eventName}
            onChange={(e) => setEventName(e.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700">Speaker</label>
          <select
            value={speakerId}
            onChange={(e) => setSpeakerId(e.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2"
            required
          >
            <option value="">Select a speaker</option>
            {speakers.map((speaker) => (
              <option key={speaker.id} value={speaker.id}>
                {speaker.name}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? 'Creating...' : 'Create Project'}
        </button>
      </form>

      <div className="bg-white rounded-lg shadow-sm border">
        <table className="min-w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Title</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Event</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Status</th>
              <th className="px-4 py-2 text-left text-sm font-medium text-gray-700">Created</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.id} className="border-t">
                <td className="px-4 py-2">{project.title}</td>
                <td className="px-4 py-2">{project.event_name || '-'}</td>
                <td className="px-4 py-2">
                  <span className="inline-flex px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800">
                    {project.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-sm text-gray-500">
                  {new Date(project.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
