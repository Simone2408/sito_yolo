from django import forms
from .models import VideoDetection

class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = VideoDetection
        fields = ['title', 'original_video']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Inserisci un titolo per il video'
            }),
            'original_video': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'video/mp4,video/avi,video/mov,video/x-matroska'
            }),
        }
        labels = {'title': 'Titolo', 'original_video': 'Carica Video'}
        help_texts = {'original_video': 'Formati supportati: MP4, AVI, MOV, MKV (max 500MB)'}

    def clean_original_video(self):
        video = self.cleaned_data.get('original_video')
        if not video:
            return video
        if video.size > 500 * 1024 * 1024:
            raise forms.ValidationError('Il file è troppo grande. Dimensione massima: 500MB')
        ext = video.name.split('.')[-1].lower()
        if ext not in ['mp4', 'avi', 'mov', 'mkv']:
            raise forms.ValidationError('Formato non supportato. Usa: mp4, avi, mov, mkv')
        return video
