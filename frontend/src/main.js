import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-quartz.css'
import './styles/reset.css'
import './styles/card.css'
import './styles/form.css'
import './styles/grid.css'
import './styles/tabs.css'
import './styles/dark.css'
import AppButton from './components/AppButton/AppButton.vue'
import AppModal from './components/AppModal/AppModal.vue'

const app = createApp(App)
app.use(router)
app.component('AppButton', AppButton)
app.component('AppModal', AppModal)
app.mount('#app')
