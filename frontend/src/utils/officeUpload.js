import api from '../api/client'

export async function uploadOfficeFile(file, projectId, category) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('project_id', projectId)
  formData.append('category', category)

  const { data } = await api.post('/documents/upload-office', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
