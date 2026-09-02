import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export function NavBar() {
  const { session, signOut } = useAuth()

  return (
    <header className="navbar">
      <NavLink to="/" className="navbar-brand">
        Rehearsal Coach
      </NavLink>
      {session && (
        <nav className="navbar-links">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <button className="link-button" onClick={() => signOut()}>
            Sign out
          </button>
        </nav>
      )}
    </header>
  )
}
