import { GlobalNav } from './components/GlobalNav'
import { PromoBanner } from './components/PromoBanner'
import { Footer } from './components/Footer'
import { Home } from './pages/Home'

function App() {
  return (
    <div id="page">
      <GlobalNav />
      <PromoBanner />
      <Home />
      <Footer />
    </div>
  )
}

export default App
