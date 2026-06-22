import { Link, createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({ component: Home })

function Home() {
  return (
    <div className="space-y-6">
      <div className="bg-white p-8 rounded-lg shadow-sm border">
        <h1 className="text-3xl font-bold text-gray-900">Repurposer</h1>
        <p className="mt-2 text-gray-600">
          Turn speeches into short videos, LinkedIn posts, and quote cards.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Link
          to="/speakers"
          className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow"
        >
          <h2 className="text-xl font-semibold">Speakers</h2>
          <p className="mt-1 text-gray-600">Manage speakers and their style personas.</p>
        </Link>

        <Link
          to="/projects"
          className="bg-white p-6 rounded-lg shadow-sm border hover:shadow-md transition-shadow"
        >
          <h2 className="text-xl font-semibold">Projects</h2>
          <p className="mt-1 text-gray-600">Create projects and generate content.</p>
        </Link>
      </div>
    </div>
  )
}
