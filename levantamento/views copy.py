from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Projeto, Beneficiario, Confrontante, Vertice
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import io, math
from django.http import HttpResponse
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY  # Importar constantes de alinhamento
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from reportlab.lib import colors
from io import BytesIO
from pyproj import Transformer
from reportlab.pdfbase.pdfmetrics import stringWidth


#Calcular Largura da coluna Confrontantes

def calcular_largura_confrontantes(tabela_dados, coluna=4, fonte='Times-Roman', tamanho=10):
    maior_largura = 0.0

    for linha in tabela_dados:
        texto = str(linha[coluna])
        largura = float(stringWidth(texto, fonte, tamanho))

        if largura > maior_largura:
            maior_largura = largura

    return maior_largura + 15


# Calcular Azimute

def gms_para_decimal(valor):
    """
    Converte '48°28'11.37" O' ou '27°12'33.12" S' para decimal
    """
    valor = valor.strip().replace(",", ".")

    if "°" in valor:
        direcao = valor[-1].upper()

        valor = valor.replace("O", "").replace("W", "").replace("S", "").replace("N", "")
        graus, resto = valor.split("°")
        minutos, resto = resto.split("'")
        segundos = resto.replace('"', "").strip()

        decimal = float(graus) + float(minutos)/60 + float(segundos)/3600

        if direcao in ["O", "W", "S"]:
            decimal = -decimal

        return decimal

    return float(valor)

def br(valor, casas=2):
    try:
        return f"{float(valor):.{casas}f}".replace(".", ",")
    except:
        return "0,00"


def br_coord(valor, casas=3):
    try:
        return f"{float(valor):.{casas}f}".replace(".", ",")
    except:
        return "0,000"


def decimal_para_gms(angulo):
    graus = int(angulo)
    minutos_float = (angulo - graus) * 60
    minutos = int(minutos_float)
    segundos = (minutos_float - minutos) * 60
    return f"{graus}°{minutos:02d}'{segundos:05.2f}\""

def calcular_azimute_utm(e1, n1, e2, n2):
    delta_e = e2 - e1
    delta_n = n2 - n1

    azimute = math.degrees(math.atan2(delta_e, delta_n))
    azimute = (azimute + 360) % 360

    return decimal_para_gms(azimute)

def calcular_azimute(lat1, lon1, lat2, lon2):
    lat1 = math.radians(gms_para_decimal(lat1))
    lon1 = math.radians(gms_para_decimal(lon1))
    lat2 = math.radians(gms_para_decimal(lat2))
    lon2 = math.radians(gms_para_decimal(lon2))


    dlon = lon2 - lon1

    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    azimute = math.degrees(math.atan2(x, y))
    azimute = (azimute + 360) % 360

    return decimal_para_gms(azimute)

def importar_utm(request, projeto_id):
    projeto = get_object_or_404(Projeto, id=projeto_id)

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo_utm")

        if not arquivo:
            messages.error(request, "Nenhum arquivo enviado.")
            return redirect("editar_projeto", projeto_id=projeto_id)

        linhas = arquivo.read().decode("utf-8").splitlines()
        atualizados = 0
        ignorados = 0
        erros = 0

        for linha in linhas:
            try:
                if not linha.strip():
                    continue

                partes = linha.split(",")

                nome = partes[0].strip()                # V01
                este = partes[1].strip().replace(",", ".")  # 755924.694
                norte = partes[2].strip().replace(",", ".") # 6956938.013

                # Converte para float
                este = float(este)
                norte = float(norte)

                # Busca o vértice pelo nome dentro do projeto
                vertice = Vertice.objects.filter(nome=nome, projeto=projeto).first()

                if not vertice:
                    ignorados += 1
                    continue

                # Atualiza
                vertice.utm_e = este
                vertice.utm_n = norte
                vertice.save()

                atualizados += 1

            except Exception as e:
                print("Erro linha:", linha, e)
                erros += 1

        messages.success(
            request,
            f"Importação concluída! Atualizados: {atualizados}, Ignorados: {ignorados}, Erros: {erros}"
        )

        return redirect("editar_projeto", projeto_id=projeto_id)

    return redirect("editar_projeto", projeto_id=projeto_id)



# View de login
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')  # Redireciona para a view de geração de PDF
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
            return render(request, 'levantamento/login.html')
    return render(request, 'levantamento/login.html')

# View de logout
def logout_view(request):
    logout(request)
    return redirect('login')

# View principal
@login_required
def index(request):
    projetos = Projeto.objects.all()
    beneficiarios = []
    confrontantes = []
    vertices = []
    projeto_selecionado = None

    if 'projeto_selecionado_id' in request.session:
        try:
            projeto_selecionado = Projeto.objects.get(id=request.session['projeto_selecionado_id'])
        except Projeto.DoesNotExist:
            projeto_selecionado = projetos.order_by('-id').first()
    else:
        projeto_selecionado = projetos.order_by('-id').first()

    if projeto_selecionado:
        beneficiarios = Beneficiario.objects.filter(projeto=projeto_selecionado)
        confrontantes = Confrontante.objects.filter(projeto=projeto_selecionado)
        vertices = Vertice.objects.filter(projeto=projeto_selecionado)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'selecionar_projeto':
            projeto_id = request.POST.get('projeto_filtro')
            try:
                projeto_selecionado = Projeto.objects.get(id=projeto_id)
                request.session['projeto_selecionado_id'] = projeto_id
                beneficiarios = Beneficiario.objects.filter(projeto=projeto_selecionado)
                confrontantes = Confrontante.objects.filter(projeto=projeto_selecionado)
                vertices = Vertice.objects.filter(projeto=projeto_selecionado)
            except Projeto.DoesNotExist:
                messages.error(request, 'Projeto selecionado não existe.')

        elif action == 'add_projeto':
            nome = request.POST.get('nome_projeto')
            inscricao_imobiliaria = request.POST.get('inscricao_imobiliaria')
            endereco = request.POST.get('endereco_projeto')
            area = request.POST.get('area_projeto')
            perimetro = request.POST.get('perimetro_projeto')
            epoca_medicao = request.POST.get('epoca_medicao')
            instrumento = request.POST.get('instrumento')
            try:
                projeto = Projeto.objects.create(
                    nome=nome,
                    inscricao_imobiliaria=inscricao_imobiliaria,
                    endereco=endereco,
                    area=float(area),
                    perimetro=float(perimetro),
                    epoca_medicao=epoca_medicao,
                    instrumento=instrumento
                )
                request.session['projeto_selecionado_id'] = projeto.id
                messages.success(request, 'Projeto adicionado com sucesso!')
            except ValueError as e:
                messages.error(request, f'Erro ao adicionar projeto: {str(e)}')

        elif action == 'add_beneficiario':
            projeto_id = request.POST.get('projeto_ben')
            nome = request.POST.get('nome_ben')
            cpf_cnpj = request.POST.get('cpf_cnpj_ben')
            rua = request.POST.get('rua_ben')
            numero = request.POST.get('numero_ben')
            bairro = request.POST.get('bairro_ben')
            cidade = request.POST.get('cidade_ben')
            try:
                projeto = Projeto.objects.get(id=projeto_id)
                Beneficiario.objects.create(
                    projeto=projeto,
                    nome=nome,
                    cpf_cnpj=cpf_cnpj,
                    rua=rua,
                    numero=numero,
                    bairro=bairro,
                    cidade=cidade
                )
                messages.success(request, 'Beneficiário adicionado com sucesso!')
            except Projeto.DoesNotExist:
                messages.error(request, 'Projeto selecionado não existe.')
            except Exception as e:
                messages.error(request, f'Erro ao adicionar beneficiário: {str(e)}')

        elif action == 'importar_beneficiarios':
            projeto_id = request.POST.get('projeto_ben')
            arquivo = request.FILES.get('arquivo_beneficiarios')
            
            if projeto_id and arquivo:
                try:
                    projeto = Projeto.objects.get(id=projeto_id)
                    try:
                        conteudo = arquivo.read().decode('utf-8').splitlines()
                    except UnicodeDecodeError:
                        arquivo.seek(0)
                        try:
                            conteudo = arquivo.read().decode('latin-1').splitlines()
                        except UnicodeDecodeError:
                            arquivo.seek(0)
                            conteudo = arquivo.read().decode('windows-1252').splitlines()
                    
                    for linha in conteudo:
                        campos = linha.strip().split('\t')
                        if len(campos) != 6:
                            messages.error(request, f'Formato inválido na linha: {linha}')
                            continue
                        nome, cpf_cnpj, rua, numero, bairro, cidade = campos
                        
                        Beneficiario.objects.create(
                            projeto=projeto,
                            nome=nome,
                            cpf_cnpj=cpf_cnpj,
                            rua=rua,
                            numero=numero,
                            bairro=bairro,
                            cidade=cidade
                        )
                    messages.success(request, 'Beneficiários importados com sucesso!')
                except Projeto.DoesNotExist:
                    messages.error(request, 'Projeto selecionado não existe.')
                except Exception as e:
                    messages.error(request, f'Erro ao importar beneficiários: {str(e)}')
            else:
                messages.error(request, 'Selecione um projeto e um arquivo TXT.')

        elif action == 'edit_beneficiario':
            beneficiario_id = request.POST.get('beneficiario_id')
            nome = request.POST.get('nome_ben')
            cpf_cnpj = request.POST.get('cpf_cnpj_ben')
            rua = request.POST.get('rua_ben')
            numero = request.POST.get('numero_ben')
            bairro = request.POST.get('bairro_ben')
            cidade = request.POST.get('cidade_ben')
            try:
                beneficiario = Beneficiario.objects.get(id=beneficiario_id)
                beneficiario.nome = nome
                beneficiario.cpf_cnpj = cpf_cnpj
                beneficiario.rua = rua
                beneficiario.numero = numero
                beneficiario.bairro = bairro
                beneficiario.cidade = cidade
                beneficiario.save()
                messages.success(request, 'Beneficiário atualizado com sucesso!')
            except Beneficiario.DoesNotExist:
                messages.error(request, 'Beneficiário não encontrado.')
            except Exception as e:
                messages.error(request, f'Erro ao atualizar beneficiário: {str(e)}')

        elif action == 'delete_beneficiario':
            beneficiario_id = request.POST.get('beneficiario_id')
            try:
                beneficiario = Beneficiario.objects.get(id=beneficiario_id)
                beneficiario.delete()
                messages.success(request, 'Beneficiário excluído com sucesso!')
            except Beneficiario.DoesNotExist:
                messages.error(request, 'Beneficiário não encontrado.')
            except Exception as e:
                messages.error(request, f'Erro ao excluir beneficiário: {str(e)}')

        elif action == 'add_confrontante':
            projeto_id = request.POST.get('projeto_con')
            nome = request.POST.get('nome_con')
            cpf_cnpj = request.POST.get('cpf_cnpj_con')
            direcao = request.POST.get('direcao_con')
            rua = request.POST.get('rua_con')
            numero = request.POST.get('numero_con')
            bairro = request.POST.get('bairro_con')
            cidade = request.POST.get('cidade_con')
            try:
                projeto = Projeto.objects.get(id=projeto_id)
                Confrontante.objects.create(
                    projeto=projeto,
                    nome=nome,
                    cpf_cnpj=cpf_cnpj,
                    direcao=direcao,
                    rua=rua,
                    numero=numero,
                    bairro=bairro,
                    cidade=cidade
                )
                messages.success(request, 'Confrontante adicionado com sucesso!')
            except Projeto.DoesNotExist:
                messages.error(request, 'Projeto selecionado não existe.')
            except Exception as e:
                messages.error(request, f'Erro ao adicionar confrontante: {str(e)}')

        elif action == 'edit_confrontante':
            confrontante_id = request.POST.get('confrontante_id')
            nome = request.POST.get('nome_con')
            cpf_cnpj = request.POST.get('cpf_cnpj_con')
            direcao = request.POST.get('direcao_con')
            rua = request.POST.get('rua_con')
            numero = request.POST.get('numero_con')
            bairro = request.POST.get('bairro_con')
            cidade = request.POST.get('cidade_con')
            try:
                confrontante = Confrontante.objects.get(id=confrontante_id)
                confrontante.nome = nome
                confrontante.cpf_cnpj = cpf_cnpj
                confrontante.direcao = direcao
                confrontante.rua = rua
                confrontante.numero = numero
                confrontante.bairro = bairro
                confrontante.cidade = cidade
                confrontante.save()
                messages.success(request, 'Confrontante atualizado com sucesso!')
            except Confrontante.DoesNotExist:
                messages.error(request, 'Confrontante não encontrado.')
            except Exception as e:
                messages.error(request, f'Erro ao atualizar confrontante: {str(e)}')

        elif action == 'delete_confrontante':
            confrontante_id = request.POST.get('confrontante_id')
            try:
                confrontante = Confrontante.objects.get(id=confrontante_id)
                confrontante.delete()
                messages.success(request, 'Confrontante excluído com sucesso!')
            except Confrontante.DoesNotExist:
                messages.error(request, 'Confrontante não encontrado.')
            except Exception as e:
                messages.error(request, f'Erro ao excluir confrontante: {str(e)}')

        elif action == 'toggle_confrontante_pdf':
            excluir_ids = request.POST.getlist('excluir_confrontantes')  # Lista de IDs dos confrontantes a excluir
            confrontantes = Confrontante.objects.filter(projeto__id=request.POST.get('projeto_filtro'))
            for confrontante in confrontantes:
                # Se o ID do confrontante está na lista de exclusão, marca como True, senão False
                confrontante.excluir_do_pdf = str(confrontante.id) in excluir_ids
                confrontante.save()
            messages.success(request, 'Seleção de confrontantes atualizada!')
            return redirect('index')

        elif action == 'importar_confrontantes':
            projeto_id = request.POST.get('projeto_con')
            arquivo = request.FILES.get('arquivo_confrontantes')
            
            if projeto_id and arquivo:
                try:
                    projeto = Projeto.objects.get(id=projeto_id)
                    try:
                        conteudo = arquivo.read().decode('utf-8').splitlines()
                    except UnicodeDecodeError:
                        arquivo.seek(0)
                        try:
                            conteudo = arquivo.read().decode('latin-1').splitlines()
                        except UnicodeDecodeError:
                            arquivo.seek(0)
                            conteudo = arquivo.read().decode('windows-1252').splitlines()
                    
                    for linha in conteudo:
                        campos = linha.strip().split('\t')
                        if len(campos) != 7:
                            messages.error(request, f'Formato inválido na linha: {linha}')
                            continue
                        nome, cpf_cnpj, direcao, rua, numero, bairro, cidade = campos
                        if direcao not in ['Frente', 'Fundos', 'Direito', 'Esquerdo']:
                            messages.error(request, f'Direção inválida na linha: {linha}. Use Frente, Fundos, Direito ou Esquerdo.')
                            continue
                        
                        Confrontante.objects.create(
                            projeto=projeto,
                            nome=nome,
                            cpf_cnpj=cpf_cnpj,
                            direcao=direcao,
                            rua=rua,
                            numero=numero,
                            bairro=bairro,
                            cidade=cidade
                        )
                    messages.success(request, 'Confrontantes importados com sucesso!')
                except Projeto.DoesNotExist:
                    messages.error(request, 'Projeto selecionado não existe.')
                except Exception as e:
                    messages.error(request, f'Erro ao importar confrontantes: {str(e)}')
            else:
                messages.error(request, 'Selecione um projeto e um arquivo TXT.')

        elif action == 'importar_vertices':
            projeto_id = request.POST.get('projeto_ver')
            arquivo = request.FILES.get('arquivo_vertices')
            
            if projeto_id and arquivo:
                try:
                    projeto = Projeto.objects.get(id=projeto_id)
                    try:
                        conteudo = arquivo.read().decode('utf-8').splitlines()
                    except UnicodeDecodeError:
                        arquivo.seek(0)
                        try:
                            conteudo = arquivo.read().decode('latin-1').splitlines()
                        except UnicodeDecodeError:
                            arquivo.seek(0)
                            conteudo = arquivo.read().decode('windows-1252').splitlines()
                    
                    for linha in conteudo:
                        campos = linha.strip().split('\t')
                        if len(campos) < 6:
                            messages.error(request, f'Formato inválido na linha: {linha}')
                            continue
                        de_vertice, para_vertice, longitude, latitude, distancia, confrontante_nome = campos[:6]
                        confrontante_cpf_cnpj = campos[6] if len(campos) > 6 else ''
                        
                        utm_n = float(campos[6].replace(",", "."))
                        utm_e = float(campos[7].replace(",", "."))

                        vertice_data = {
                            'projeto': projeto,
                            'de_vertice': de_vertice,
                            'para_vertice': para_vertice,
                            'longitude': longitude,
                            'latitude': latitude,
                            'utm_n': utm_n,
                            'utm_e': utm_e,
                            'distancia': float(distancia.replace(",", ".")),
                            'confrontante_texto': confrontante_nome
                        }
                        if confrontante_cpf_cnpj:
                            try:
                                confrontante = Confrontante.objects.get(cpf_cnpj=confrontante_cpf_cnpj, projeto=projeto)
                                vertice_data['confrontante'] = confrontante
                                vertice_data['confrontante_texto'] = ''
                            except Confrontante.DoesNotExist:
                                pass
                        Vertice.objects.create(**vertice_data)
                    messages.success(request, 'Vértices importados com sucesso!')
                except Projeto.DoesNotExist:
                    messages.error(request, 'Projeto selecionado não existe.')
                except ValueError as e:
                    messages.error(request, f'Erro ao importar vértices: {str(e)}')
                except Exception as e:
                    messages.error(request, f'Erro inesperado: {str(e)}')
            else:
                messages.error(request, 'Selecione um projeto e um arquivo TXT.')

        elif action == 'importar_utm':
            projeto_id = request.POST.get('projeto_ver')
            arquivo = request.FILES.get('arquivo_utm')

            if projeto_id and arquivo:
                try:
                    projeto = Projeto.objects.get(id=projeto_id)
                    vertices = Vertice.objects.filter(projeto=projeto).order_by("id")

                    try:
                        linhas = arquivo.read().decode("utf-8").splitlines()
                    except UnicodeDecodeError:
                        arquivo.seek(0)
                        linhas = arquivo.read().decode("latin-1").splitlines()

                    if len(linhas) != vertices.count():
                        messages.error(request, "Quantidade de linhas no arquivo não confere com os vértices.")
                        return redirect("index")

                    atualizados = 0

                    for i, linha in enumerate(linhas):
                        partes = linha.replace(",", " ").split()

                        utm_n = float(partes[-2].replace(",", "."))
                        utm_e = float(partes[-1].replace(",", "."))

                        vertice = vertices[i]

                        # ✅ SOMENTE SE NÃO TIVER UTM AINDA
                        if not vertice.utm_n or not vertice.utm_e:
                            vertice.utm_n = utm_n
                            vertice.utm_e = utm_e
                            vertice.save()
                            atualizados += 1

                    messages.success(request, f"{atualizados} vértices atualizados com UTM.")
                except Projeto.DoesNotExist:
                    messages.error(request, "Projeto não encontrado.")
                except Exception as e:
                    messages.error(request, f"Erro ao importar UTM: {str(e)}")
            else:
                messages.error(request, "Selecione um projeto e um arquivo.")


        elif action == 'add_vertice':
            projeto_id = request.POST.get('projeto_ver')
            de_vertice = request.POST.get('de_vertice')
            para_vertice = request.POST.get('para_vertice')
            longitude = request.POST.get('longitude_ver')
            latitude = request.POST.get('latitude_ver')
            distancia = request.POST.get('distancia_ver') or request.POST.get('edit_distancia_ver')
            if distancia:
                distancia = distancia.replace(",", ".")
                try:
                    distancia = float(distancia)
                except ValueError:
                    distancia = 0.0
            else:
                distancia = 0.0
            utm_n = request.POST.get('utm_n_ver')
            utm_e = request.POST.get('utm_e_ver')
            confrontante_id = request.POST.get('confrontante_ver')
            confrontante_texto = request.POST.get('confrontante_texto')
            try:
                projeto = Projeto.objects.get(id=projeto_id)
                distancia = float(distancia) if distancia else 0.0
                vertice_data = {
                    'projeto': projeto,
                    'de_vertice': de_vertice,
                    'para_vertice': para_vertice,
                    'longitude': longitude,
                    'latitude': latitude,
                    'distancia': distancia,
                    'utm_n': utm_n,
                    'utm_e': utm_e,
                    'confrontante_texto': confrontante_texto
                }
                if confrontante_id:
                    confrontante = Confrontante.objects.get(id=confrontante_id, projeto=projeto)
                    vertice_data['confrontante'] = confrontante
                    vertice_data['confrontante_texto'] = ''
                Vertice.objects.create(**vertice_data)
                messages.success(request, 'Vértice adicionado com sucesso!')
            except Projeto.DoesNotExist:
                messages.error(request, 'Projeto selecionado não existe.')
            except Confrontante.DoesNotExist:
                messages.error(request, 'Confrontante selecionado não existe.')
            except ValueError as e:
                messages.error(request, f'Erro ao adicionar vértice: {str(e)}')
            except Exception as e:
                messages.error(request, f'Erro inesperado: {str(e)}')

        elif action == 'edit_vertice':
            vertice_id = request.POST.get('vertice_id')
            de_vertice = request.POST.get('de_vertice')
            para_vertice = request.POST.get('para_vertice')
            longitude = request.POST.get('longitude_ver')
            latitude = request.POST.get('latitude_ver')
            distancia = request.POST.get('distancia_ver')
            utm_n_raw = request.POST.get('utm_n_raw')
            utm_e_raw = request.POST.get('utm_e_raw')


            
            # ✅ CORREÇÃO DEFINITIVA PARA VÍRGULA
            if distancia:
                distancia = distancia.replace(",", ".")
                try:
                    distancia = float(distancia)
                except ValueError:
                    distancia = 0.0
            else:
                distancia = 0.0
            confrontante_id = request.POST.get('confrontante_ver')
            confrontante_texto = request.POST.get('confrontante_texto')
            try:
                vertice = Vertice.objects.get(id=vertice_id)
                distancia = float(distancia) if distancia else 0.0
                vertice.de_vertice = de_vertice
                vertice.para_vertice = para_vertice
                vertice.longitude = longitude
                vertice.latitude = latitude
                vertice.distancia = distancia
                vertice.utm_n = utm_n
                vertice.utm_e = utm_e
                vertice.confrontante_texto = confrontante_texto
                if confrontante_id:
                    confrontante = Confrontante.objects.get(id=confrontante_id)
                    vertice.confrontante = confrontante
                    vertice.confrontante_texto = ''
                else:
                    vertice.confrontante = None
                vertice.save()
                messages.success(request, 'Vértice atualizado com sucesso!')
            except Vertice.DoesNotExist:
                messages.error(request, 'Vértice não encontrado.')
            except Confrontante.DoesNotExist:
                messages.error(request, 'Confrontante selecionado não existe.')
            except ValueError as e:
                messages.error(request, f'Erro ao atualizar vértice: {str(e)}')
            except Exception as e:
                messages.error(request, f'Erro inesperado: {str(e)}')

        elif action == 'delete_vertice':
            vertice_id = request.POST.get('vertice_id')
            try:
                vertice = Vertice.objects.get(id=vertice_id)
                vertice.delete()
                messages.success(request, 'Vértice excluído com sucesso!')
            except Vertice.DoesNotExist:
                messages.error(request, 'Vértice não encontrado.')
            except Exception as e:
                messages.error(request, f'Erro ao excluir vértice: {str(e)}')

        elif action == 'gerar_memorial_pdf':
            projeto_id = request.POST.get('projeto_memorial')
            try:
                projeto = Projeto.objects.get(id=projeto_id)
                vertices = Vertice.objects.filter(projeto=projeto)
                beneficiarios = Beneficiario.objects.filter(projeto=projeto)
                confrontantes = Confrontante.objects.filter(projeto=projeto, excluir_do_pdf=False)



                # Log para depuração
                print(f"Projeto ID (PDF): {projeto_id}")
                print(f"Beneficiários encontrados (PDF): {len(beneficiarios)}")
                print(f"Confrontantes encontrados (PDF): {len(confrontantes)}")
                print(f"Vértices encontrados (PDF): {len(vertices)}")

                # Buffer para o PDF
                buffer = io.BytesIO()
                doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2.5*cm, leftMargin=2.5*cm, topMargin=2*cm, bottomMargin=1.5*cm)
                elements = []

                # Estilos
                styles = getSampleStyleSheet()
                title_style = ParagraphStyle(
                    'TitleStyle',
                    parent=styles['Heading1'],
                    fontName='Times-Roman',
                    fontSize=16,
                    alignment=1,  # Centro
                    spaceAfter=12,
                    textTransform='uppercase',
                    fontWeight='bold',
                    underline=True
                )
                heading_style = ParagraphStyle(
                    'HeadingStyle',
                    parent=styles['Heading2'],
                    fontName='Times-Roman',
                    fontSize=14,
                    spaceAfter=12,
                    fontWeight='bold'
                )
                normal_style = ParagraphStyle(
                    'NormalStyle',
                    parent=styles['Normal'],
                    fontName='Times-Roman',
                    fontSize=12,
                    spaceAfter=12,
                    firstLineIndent=1.25*cm,
                    alignment=4,  # Justificado
                    leading=5  # Espaçamento de 1,5 linhas (12pt * 1.5 = 18pt)
                )
                descricao_style = ParagraphStyle(
                    'DescricaoStyle',
                    parent=styles['Normal'],
                    fontName='Times-Roman',
                    fontSize=12,
                    spaceAfter=12,
                    firstLineIndent=1.25*cm,
                    alignment=TA_JUSTIFY,
                    leading=18   # 12pt * 1,5 = ESPAÇAMENTO CORRETO
                )
                center_style = ParagraphStyle(
                    'CenterStyle',
                    parent=styles['Normal'],
                    fontName='Times-Roman',
                    fontSize=12,
                    spaceAfter=12,
                    alignment=1  # Centro
                )
                left_style = ParagraphStyle(
                    'LeftStyle',
                    parent=styles['Normal'],
                    fontName='Times-Roman',
                    fontSize=12,
                    spaceAfter=12,
                    alignment=0  # Left
                )
                # Estilo para seções (negrito, alinhado à esquerda)
                section_style = ParagraphStyle(
                    'SectionStyle',
                    parent=styles['Normal'],
                    fontName='Times-Roman',
                    fontSize=14,
                    spaceAfter=12,
                    fontWeight='bold'
                )

                # Título principal
                elements.append(Paragraph("MEMORIAL DESCRITIVO", title_style))
                elements.append(Paragraph("<br/><br/>", normal_style))  # Linhas em branco

                # Seção 1: Beneficiário(s)
                elements.append(Paragraph("1. Beneficiário(s):", section_style))
                if beneficiarios:
                    # Cabeçalho da tabela
                    header_data = [["Nome", "CPF"]]
                    header_table = Table(header_data, colWidths=[10*cm, 6*cm])
                    header_table.setStyle(TableStyle([
                        #('BACKGROUND', (0, 0), (-1, 0), '#d3d3d3'),
                        ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, -1), 'Times-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                        #('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ]))
                    elements.append(header_table)

                    # Dados dos beneficiários
                    data = []
                    for ben in beneficiarios:
                        data.append([Paragraph(ben.nome, ParagraphStyle('Bold', fontName='Times-Bold', fontSize=12)), ben.cpf_cnpj,])
                    table_ben = Table(data, colWidths=[10*cm, 6*cm])
                    table_ben.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
                        ('FONTSIZE', (0, 0), (-1, -1), 12),
                        ('ALIGN', (1, 0), (1, -1), 'CENTER'),  # Centralizar apenas a coluna CPF (índice 1)
                        #('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ]))
                    elements.append(table_ben)
                else:
                    elements.append(Paragraph("Nenhum beneficiário registrado.", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 2: Localização do Imóvel
                elements.append(Paragraph("2. Localização do Imóvel:", heading_style))
                
                if projeto.inscricao_imobiliaria and projeto.inscricao_imobiliaria.strip():
                    elements.append(Paragraph(f"Inscrição Imobiliária: {projeto.inscricao_imobiliaria}", normal_style))
                
                elements.append(Paragraph(f"{projeto.endereco}", descricao_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 3: Área
                elements.append(Paragraph("3. Área:", heading_style))
                elements.append(Paragraph(f"{projeto.area}m²".replace(".",","), normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 4: Perímetro
                elements.append(Paragraph("4. Perímetro:", heading_style))
                elements.append(Paragraph(f"{projeto.perimetro} m".replace(".",","), normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 5: Época da Medição
                elements.append(Paragraph("5. Época da Medição:", heading_style))
                elements.append(Paragraph(f"{projeto.epoca_medicao}", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 6: Instrumento Utilizado
                elements.append(Paragraph("6. Instrumento Utilizado:", heading_style))
                elements.append(Paragraph(f"{projeto.instrumento}", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 7: Sistema Geodésico de Referência
                elements.append(Paragraph("7. Sistema Geodésico de Referência:", heading_style))
                elements.append(Paragraph("SIRGAS 2000", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 8: Projeção Cartográfica de Distância e Área
                elements.append(Paragraph("8. Projeção Cartográfica de Distância e Área:", heading_style))
                elements.append(Paragraph("UTM", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 9: Tabela de Coordenadas, Confrontações e Medidas
                elements.append(Paragraph("9. Tabela de Coordenadas, Confrontações e Medidas:", heading_style))

                data = [['VÉRTICE', 'LATITUDE', 'LONGITUDE', 'DIST.(m)', 'CONFRONTANTE']]

                if vertices:
                    for v in vertices:
                        data.append([
                            str(v.de_vertice),
                            str(v.latitude),
                            str(v.longitude).replace("O","W"),
                            f'{float(v.distancia):.2f}'.replace(".",","),
                            str(v.confrontante.nome if v.confrontante else v.confrontante_texto)
                        ])
                else:
                    data.append(["Nenhum vértice registrado.", "", "", "", ""])

                #Largura Automáticas da coluna Confrontantes

                largura_confrontantes = calcular_largura_confrontantes(data)
                larguras = [2*cm, 3*cm, 3*cm, 2*cm, largura_confrontantes]

                #Blindagem contra lista em qualquer coluna
                # ✅ Larguras fixas e proporcionais à página A4
                larguras = [
                    2 * cm,    # Vértice
                    3.2 * cm,  # Latitude
                    3.2 * cm,  # Longitude
                    2.5 * cm,  # Distância
                    max(largura_confrontantes, 7 * cm)  # ✅ Nunca fica estreita
                ]

                # ✅ CRIA A TABELA CORRETAMENTE
                table = Table(data, colWidths=larguras, repeatRows=1)

                print("LARGURA CONFRONTANTES =>", largura_confrontantes, type(largura_confrontantes))

                table.setStyle(TableStyle([
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('FONTNAME', (0, 0), (-1, -1), 'Times-Roman'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    #Alinhamento Geral
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    #Alinhamento a Esquerda Confrontantes
                    ('ALIGN', (4,1), (4,-1), 'LEFT'),
                ]))

                elements.append(table)
                elements.append(Paragraph("<br/><br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Seção 10: Descrição Perimétrica
                elements.append(Paragraph("10. Descrição Perimétrica:", heading_style))

                #Paragraph("10. Observação Complementar:", heading_style)
                #elements.append(Paragraph("O imóvel objeto deste memorial descritivo apresenta testada para duas vias públicas, sendo a Rua Maria Píres Linhares, no segmento entre os vértices V01 e V02, com extensão de 20,85 metros, e a Servidão Aristides Costa, no segmento entre os vértices V04 e V05, com extensão de 20,79 metros. Tal condição caracteriza o imóvel como de testada dupla, estando esta conformação representada na planta topográfica anexa e descrita na tabela de confrontações", normal_style))
                #elements.append(Paragraph("<br/>", normal_style))


                # if vertices and len(vertices) > 2:
                #     lista_vertices = list(vertices)

                #     texto = "Inicia-se a descrição deste perímetro no ponto de vértice "

                #     v_inicio = lista_vertices[0]
                #     n = v_inicio.utm_n
                #     e = v_inicio.utm_e

                #     texto += f"{v_inicio.de_vertice}, de coordenadas N {br_coord(n)}m e E {br_coord(e)}m; "

                #     for i in range(len(lista_vertices) - 1):
                #         v1 = lista_vertices[i]
                #         v2 = lista_vertices[i + 1]

                #         #azimute = calcular_azimute(
                #         #    v1.latitude, v1.longitude,
                #         #   v2.latitude, v2.longitude
                #         #)
                #         azimute = calcular_azimute_utm(
                #             v1.utm_e, v1.utm_n,
                #             v2.utm_e, v2.utm_n
                #         )

                #         distancia = br(v1.distancia)
                #         n2 = v2.utm_n
                #         e2 = v2.utm_e

                #         confrontante = v1.confrontante.nome if v1.confrontante else v1.confrontante_texto
                #         # CPF/CNPJ do confrontante (se existir)
                #         confrontante_doc = ""
                #         if v1.confrontante and v1.confrontante.cpf_cnpj:

                #             doc_raw = v1.confrontante.cpf_cnpj
                #             doc_numbers = "".join(filter(str.isdigit, doc_raw))

                #             tipo = ""
                #             if len(doc_numbers) == 11:
                #                 tipo = "CPF"
                #             elif len(doc_numbers) == 14:
                #                 tipo = "CNPJ"

                #             if tipo:
                #                 confrontante_doc = f" {tipo}: {doc_raw}"
                #             else:
                #                 confrontante_doc = f" {doc_raw}"


                #         texto += (
                #             f"deste segue confrontando com {confrontante}, {confrontante_doc}, "
                #             f"com os seguintes azimutes e distâncias: {azimute}, {distancia}m, "
                #             f"até o vértice {v2.de_vertice}, de coordenadas "
                #             f"N {br_coord(n2)}m e E {br_coord(e2)}m; "
                #         )

                lista_vertices = list(vertices)
                total = len(lista_vertices)

                if total < 3:
                    elements.append(
                        Paragraph(
                            "Não há vértices suficientes para gerar a descrição perimétrica.",
                            normal_style
                        )
                    )
                else:
                    texto = "Inicia-se a descrição deste perímetro no ponto de vértice "

                    v_inicio = lista_vertices[0]
                    texto += (
                        f"{v_inicio.de_vertice}, de coordenadas "
                        f"N {br_coord(v_inicio.utm_n)}m e "
                        f"E {br_coord(v_inicio.utm_e)}m; "
                    )

                    for i in range(total):
                        v1 = lista_vertices[i]
                        v2 = lista_vertices[(i + 1) % total]

                        azimute = calcular_azimute_utm(
                            v1.utm_e, v1.utm_n,
                            v2.utm_e, v2.utm_n
                        )

                        distancia = br(v1.distancia)

                        confrontante = (
                            v1.confrontante.nome
                            if v1.confrontante
                            else v1.confrontante_texto
                        )

                        confrontante_doc = ""
                        if v1.confrontante and v1.confrontante.cpf_cnpj:
                            doc_raw = v1.confrontante.cpf_cnpj
                            doc_numbers = "".join(filter(str.isdigit, doc_raw))

                            if len(doc_numbers) == 11:
                                confrontante_doc = f" CPF: {doc_raw}"
                            elif len(doc_numbers) == 14:
                                confrontante_doc = f" CNPJ: {doc_raw}"

                        texto += (
                            f"deste segue confrontando com {confrontante},{confrontante_doc}, "
                            f"com azimute de {azimute} e distância de {distancia}m, "
                            f"até o vértice {v2.de_vertice}, de coordenadas "
                            f"N {br_coord(v2.utm_n)}m e E {br_coord(v2.utm_e)}m; "
                        )

                    # 🔒 TEXTO FINAL — UMA ÚNICA VEZ
                    texto += (
                        "Todas as coordenadas aqui descritas estão georreferenciadas ao Sistema Geodésico Brasileiro "
                        "e encontram-se representadas no Sistema UTM, referenciadas ao Meridiano Central 51º WGr, "
                        "tendo como Datum o SIRGAS2000. Todos os azimutes e distâncias, área e perímetro foram "
                        f"calculados no plano de projeção UTM. Encerrado o perímetro total de {projeto.perimetro} m "
                        f"e área de {br(projeto.area)} m²."
                    )

                    elements.append(Paragraph(texto, descricao_style))
                # else:
                #    elements.append(Paragraph("Não há vértices suficientes para gerar a descrição perimétrica.", normal_style))


                # Local e Data
                # Obter a data atual
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                data_atual = datetime.now()

                # Dicionário para traduzir os meses para o português
                meses = {
                    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
                    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
                }

                # Formatar a data no formato desejado (ex.: "28 de Abril de 2025")
                data_formatada = f"{data_atual.day} de {meses[data_atual.month]} de {data_atual.year}"

                # Adicionar o parágrafo com a data atual
                beneficiario = projeto.beneficiarios.first()
                cidade_beneficiario = beneficiario.cidade if beneficiario else "Cidade não especificada"
                elements.append(Paragraph(f"{cidade_beneficiario}, {data_formatada}.", left_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Assinatura do Responsável Técnico
                elements.append(Paragraph("__________________________________________________", center_style))
                elements.append(Paragraph("Everton Valdir Pinto Vieira", ParagraphStyle('BoldCenter', parent=center_style, fontName='Times-Bold', fontWeight='bold')))
                elements.append(Paragraph("Resp. Técnico em Agrimensura", center_style))
                elements.append(Paragraph("CFT 02544161957", center_style))
                elements.append(Paragraph("<br/>", center_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))
                elements.append(Paragraph("<br/>", normal_style))

                # Tabela de Assinaturas (Requerentes e Confrontantes)
                all_signatures = [(ben.nome, ben.cpf_cnpj, "Requerente") for ben in beneficiarios] + \
                                [(con.nome, con.cpf_cnpj, "Confrontante") for con in confrontantes]
                if all_signatures:
                    signature_data = []
                    for i in range(0, len(all_signatures), 2):
                        row = ["", "", ""]
                        # Primeira coluna
                        nome1, cpf1, tipo1 = all_signatures[i]
                        text1 = f"{nome1}<br/>CPF: {cpf1}<br/>{tipo1}"
                        style1 = ParagraphStyle('Signature', fontName='Times-Roman', fontSize=12, leading=14)
                        if nome1 in ["Alcides De Oliveira", "Maria Aparecida Trindade Oliveira"]:
                            text1 = f"<u>{nome1}</u><br/>CPF: {cpf1}<br/>{tipo1}"
                        row[0] = Paragraph(text1, style1)
                        # Segunda coluna (espaço)
                        row[1] = ""
                        # Terceira coluna (se houver)
                        if i + 1 < len(all_signatures):
                            nome2, cpf2, tipo2 = all_signatures[i + 1]
                            text2 = f"{nome2}<br/>CPF: {cpf2}<br/>{tipo2}"
                            style2 = ParagraphStyle('Signature', fontName='Times-Roman', fontSize=12, leading=14)
                            if nome2 in ["Alcides De Oliveira", "Maria Aparecida Trindade Oliveira"]:
                                text2 = f"<u>{nome2}</u><br/>CPF: {cpf2}<br/>{tipo2}"
                            row[2] = Paragraph(text2, style2)
                        signature_data.append(row)
                        # Adicionar duas linhas vazias após cada par de assinaturas
                        signature_data.append(["", "", ""])  # Primeira linha vazia
                        signature_data.append(["", "", ""])  # Segunda linha vazia
                        signature_data.append(["", "", ""])  # Segunda linha vazia

                    table_sign = Table(signature_data, colWidths=[8*cm, 1*cm, 7*cm])
                    table_sign.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ]))
                    elements.append(table_sign)
                else:
                    elements.append(Paragraph("Nenhuma assinatura registrada.", normal_style))

                # Gerar o PDF
                doc.build(elements)
                buffer.seek(0)

                response = HttpResponse(
                    buffer.getvalue(),
                    content_type='application/pdf'
                )
                response['Content-Disposition'] = f'attachment; filename="{projeto.nome} - Memorial.pdf"'
                return response
            except Projeto.DoesNotExist:
                messages.error(request, 'Projeto selecionado não existe.')
            except Exception as e:
                messages.error(request, f'Erro ao gerar memorial em PDF: {str(e)}')
                print(f"Erro detalhado (PDF): {str(e)}")

        if projeto_selecionado:
            beneficiarios = Beneficiario.objects.filter(projeto=projeto_selecionado)
            confrontantes = Confrontante.objects.filter(projeto=projeto_selecionado)
            vertices = Vertice.objects.filter(projeto=projeto_selecionado)

    return render(request, 'levantamento/index.html', {
        'projetos': projetos,
        'beneficiarios': beneficiarios,
        'confrontantes': confrontantes,
        'vertices': vertices,
        'projeto_selecionado': projeto_selecionado
    })