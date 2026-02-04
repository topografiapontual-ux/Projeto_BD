from django.db import models
from django.core.validators import RegexValidator

class Projeto(models.Model):
    nome = models.CharField(max_length=200)
    inscricao_imobiliaria = models.CharField(
        "Inscrição Imobiliária",
        max_length=100,
        blank=True,
        null=True
    )

    endereco = models.TextField()
    area = models.FloatField(help_text="Área em metros quadrados")
    perimetro = models.FloatField(help_text="Perímetro em metros")
    epoca_medicao = models.CharField(max_length=50, help_text="Março de 2025")
    instrumento = models.CharField(max_length=100, help_text="GNSS ComNav T30")

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Projeto"
        verbose_name_plural = "Projetos"

class Beneficiario(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name='beneficiarios')
    nome = models.CharField(max_length=200)
    cpf_cnpj = models.CharField(
        max_length=18,
        validators=[
            RegexValidator(
                regex=r'^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$',
                message="Digite um CPF (XXX.XXX.XXX-XX) ou CNPJ (XX.XXX.XXX/XXXX-XX) válido."
            )
        ]
    )
    rua = models.CharField(max_length=200)
    numero = models.CharField(max_length=20)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.nome} ({self.cpf_cnpj})"

    class Meta:
        verbose_name = "Beneficiário"
        verbose_name_plural = "Beneficiários"

class Confrontante(models.Model):
    DIRECAO_CHOICES = [
        ('Direita', 'Direita'),
        ('Esquerda', 'Esquerda'),
        ('Frente', 'Frente'),
        ('Fundos', 'Fundos'),
    ]

    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name='confrontantes')
    nome = models.CharField(max_length=200)
    cpf_cnpj = models.CharField(
        max_length=18,
        validators=[
            RegexValidator(
                regex=r'^\d{3}\.\d{3}\.\d{3}-\d{2}$|^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$',
                message="Digite um CPF (XXX.XXX.XXX-XX) ou CNPJ (XX.XXX.XXX/XXXX-XX) válido."
            )
        ]
    )
    direcao = models.CharField(max_length=10, choices=DIRECAO_CHOICES)
    rua = models.CharField(max_length=200)
    numero = models.CharField(max_length=20)
    bairro = models.CharField(max_length=100)
    cidade = models.CharField(max_length=100)
    # Novo campo para marcar se o confrontante deve ser excluído do PDF
    excluir_do_pdf = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nome} ({self.direcao})"

    class Meta:
        verbose_name = "Confrontante"
        verbose_name_plural = "Confrontantes"

class Vertice(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name='vertices')
    de_vertice = models.CharField(max_length=10, help_text="Ex.: V01")
    para_vertice = models.CharField(max_length=10, help_text="Ex.: V02")
    longitude = models.CharField(max_length=20, help_text="Ex.: 48°29'05.593\" O")
    latitude = models.CharField(max_length=20, help_text="Ex.: 27°27'16.418\" S")
    distancia = models.FloatField(help_text="Distância em metros")
    utm_n = models.FloatField(null=True, blank=True)
    utm_e = models.FloatField(null=True, blank=True)
    confrontante = models.ForeignKey(Confrontante, on_delete=models.SET_NULL, null=True, blank=True, help_text="Confrontante associado ou vazio")
    confrontante_texto = models.CharField(max_length=200, blank=True, help_text="Nome do confrontante se não for um registro, ex.: Rua do Lamim, APP")

    def __str__(self):
        return f"{self.de_vertice} -> {self.para_vertice} ({self.projeto.nome})"

    class Meta:
        verbose_name = "Vértice"
        verbose_name_plural = "Vértices"