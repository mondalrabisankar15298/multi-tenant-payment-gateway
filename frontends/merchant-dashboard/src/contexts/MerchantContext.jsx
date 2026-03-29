import { createContext, useContext, useState, useEffect } from 'react'
import { api } from '../api/client'

const MerchantContext = createContext()

export function MerchantProvider({ children }) {
  const [merchants, setMerchants] = useState([])
  const [selectedMerchant, _setSelectedMerchant] = useState(null)
  const [loading, setLoading] = useState(true)

  // Wrapper to sync state, localStorage, and API client headers
  const setSelectedMerchant = (merchant) => {
    _setSelectedMerchant(merchant)
    if (merchant) {
      localStorage.setItem('selected_merchant_id', merchant.merchant_id)
      api.setApiKey(merchant.api_key)
    } else {
      localStorage.removeItem('selected_merchant_id')
      api.setApiKey(null)
    }
  }

  useEffect(() => {
    api.getMerchants().then(data => {
      setMerchants(data)
      
      const savedId = localStorage.getItem('selected_merchant_id')
      const savedMerchant = data.find(m => String(m.merchant_id) === String(savedId))
      
      if (savedMerchant) {
        setSelectedMerchant(savedMerchant)
      } else if (data.length > 0) {
        setSelectedMerchant(data[0]) // Default to 1st merchant
      }

      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  return (
    <MerchantContext.Provider value={{ merchants, selectedMerchant, setSelectedMerchant, loading }}>
      {children}
    </MerchantContext.Provider>
  )
}

export const useMerchant = () => useContext(MerchantContext)
