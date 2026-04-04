import { createContext, useContext, useState, useEffect } from 'react'
import { api, setApiKey } from '../api/client'

const MerchantContext = createContext()
const STORAGE_KEY = 'selectedMerchantId'

export function MerchantProvider({ children }) {
  const [merchants, setMerchants] = useState([])
  const [selectedMerchant, setSelectedMerchantState] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchMerchants = async () => {
    try {
      const res = await api.getMerchants()
      const data = res.data || res
      setMerchants(data)

      if (data.length > 0) {
        const savedId = localStorage.getItem(STORAGE_KEY)
        const savedMerchant = savedId
          ? data.find(m => String(m.merchant_id) === savedId)
          : null

        const toSelect = savedMerchant || data[0]
        setApiKey(toSelect.api_key)
        setSelectedMerchantState(toSelect)
      }
    } catch (err) {
      console.error('Failed to fetch merchants:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMerchants()
  }, [])

  // Synchronously set api key BEFORE React re-renders (avoids race with page useEffects)
  const setSelectedMerchant = (merchant) => {
    setApiKey(merchant?.api_key || null)
    setSelectedMerchantState(merchant)
    if (merchant) {
      localStorage.setItem(STORAGE_KEY, String(merchant.merchant_id))
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  return (
    <MerchantContext.Provider value={{
      merchants,
      selectedMerchant,
      setSelectedMerchant,
      loading,
      refreshMerchants: fetchMerchants,
    }}>
      {children}
    </MerchantContext.Provider>
  )
}

export const useMerchant = () => useContext(MerchantContext)
